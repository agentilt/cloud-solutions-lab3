import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

from cdk_app.agent_stack import AgentStack
from cdk_app.api_stack import ApiStack
from cdk_app.auth_stack import AuthStack
from cdk_app.frontend_stack import FrontendDeploymentStack, FrontendHostingStack
from cdk_app.knowledge_stack import KnowledgeStack
from cdk_app.storage_stack import StorageStack
from cdk_app.validation_stack import ValidationStack


def _synth_all():
    app = cdk.App()
    storage = StorageStack(app, "TestStorage")
    frontend_hosting = FrontendHostingStack(app, "TestFrontendHosting")
    auth = AuthStack(
        app,
        "TestAuth",
        frontend_url=frontend_hosting.frontend_url,
    )
    validation = ValidationStack(
        app,
        "TestValidation",
        artifact_bucket=storage.data_bucket,
    )
    knowledge = KnowledgeStack(app, "TestKnowledge")
    agent = AgentStack(
        app,
        "TestAgent",
        data_table=storage.data_table,
        event_bus=storage.event_bus,
        data_bucket=storage.data_bucket,
        validation_project=validation.validation_project,
        cloudformation_execution_role=validation.cloudformation_execution_role,
        knowledge_base_id=knowledge.knowledge_base_id,
        knowledge_base_arn=knowledge.knowledge_base_arn,
    )
    api = ApiStack(
        app,
        "TestApi",
        data_bucket=storage.data_bucket,
        data_table=storage.data_table,
        user_pool=auth.user_pool,
        user_pool_client=auth.user_pool_client,
        agent_runtime_arn=agent.runtime_arn,
    )
    frontend_deployment = FrontendDeploymentStack(
        app,
        "TestFrontendDeployment",
        site_bucket=frontend_hosting.site_bucket,
        distribution=frontend_hosting.distribution,
        api_url=api.http_api.url or "",
        user_pool=auth.user_pool,
        user_pool_client=auth.user_pool_client,
        user_pool_domain_base_url=auth.user_pool_domain.base_url(),
    )
    return {
        "storage": Template.from_stack(storage),
        "frontend_hosting": Template.from_stack(frontend_hosting),
        "auth": Template.from_stack(auth),
        "validation": Template.from_stack(validation),
        "knowledge": Template.from_stack(knowledge),
        "agent": Template.from_stack(agent),
        "api": Template.from_stack(api),
        "frontend_deployment": Template.from_stack(frontend_deployment),
    }


def test_storage_has_encrypted_private_artifact_bucket_and_ttl_table():
    templates = _synth_all()
    storage = templates["storage"]
    storage.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "BucketEncryption": {
                "ServerSideEncryptionConfiguration": Match.any_value(),
            },
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            },
        },
    )
    storage.has_resource_properties(
        "AWS::DynamoDB::GlobalTable",
        Match.object_like(
            {
                "KeySchema": [
                    {"AttributeName": "pk", "KeyType": "HASH"},
                    {"AttributeName": "sk", "KeyType": "RANGE"},
                ],
                "TimeToLiveSpecification": {
                    "AttributeName": "ttl",
                    "Enabled": True,
                },
            }
        ),
    )


def test_frontend_is_private_cloudfront_with_origin_access_control():
    frontend = _synth_all()["frontend_hosting"]
    frontend.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            }
        },
    )
    frontend.resource_count_is("AWS::CloudFront::OriginAccessControl", 1)
    frontend.resource_count_is("AWS::CloudFront::Distribution", 1)


def test_api_uses_cognito_jwt_authorizer_and_project_routes():
    api = _synth_all()["api"]
    api.resource_count_is("AWS::ApiGatewayV2::Authorizer", 1)
    api.has_resource_properties(
        "AWS::ApiGatewayV2::Route",
        Match.object_like({"RouteKey": "POST /projects"}),
    )
    api.has_resource_properties(
        "AWS::ApiGatewayV2::Route",
        Match.object_like({"RouteKey": "GET /projects/{project_id}"}),
    )


def test_validation_stack_has_codebuild_and_change_set_role():
    validation = _synth_all()["validation"]
    validation.resource_count_is("AWS::CodeBuild::Project", 1)
    validation.has_resource_properties(
        "AWS::IAM::Role",
        Match.object_like(
            {
                "AssumeRolePolicyDocument": {
                    "Statement": Match.array_with(
                        [
                            Match.object_like(
                                {
                                    "Principal": {
                                        "Service": "cloudformation.amazonaws.com",
                                    }
                                }
                            )
                        ]
                    )
                }
            }
        ),
    )


def test_agent_role_can_create_but_not_execute_change_sets():
    agent = _synth_all()["agent"]
    policies = agent.find_resources("AWS::IAM::Policy")
    joined = str(policies)
    assert "cloudformation:CreateChangeSet" in joined
    assert "cloudformation:ExecuteChangeSet" not in joined


def _all_policy_statements(template):
    """Every IAM statement in a stack: standalone policies + role-inline policies."""
    statements = []
    for _lid, policy in template.find_resources("AWS::IAM::Policy").items():
        statements += policy["Properties"]["PolicyDocument"]["Statement"]
    for _lid, role in template.find_resources("AWS::IAM::Role").items():
        for inline in role["Properties"].get("Policies", []):
            statements += inline["PolicyDocument"]["Statement"]
    return statements


def test_knowledge_base_over_s3_vectors():
    kb = _synth_all()["knowledge"]
    kb.resource_count_is("AWS::Bedrock::KnowledgeBase", 1)
    kb.resource_count_is("AWS::Bedrock::DataSource", 1)
    kb.resource_count_is("AWS::S3Vectors::VectorBucket", 1)
    kb.resource_count_is("AWS::S3Vectors::Index", 1)


def test_agent_can_retrieve_from_knowledge_base():
    agent = _synth_all()["agent"]
    assert "bedrock:Retrieve" in str(agent.find_resources("AWS::IAM::Policy"))


def test_agent_has_guardrail_with_prompt_attack_filter():
    agent = _synth_all()["agent"]
    agent.resource_count_is("AWS::Bedrock::Guardrail", 1)
    agent.has_resource_properties(
        "AWS::Bedrock::Guardrail",
        Match.object_like(
            {
                "ContentPolicyConfig": {
                    "FiltersConfig": Match.array_with([Match.object_like({"Type": "PROMPT_ATTACK"})])
                }
            }
        ),
    )
    assert "bedrock:ApplyGuardrail" in str(agent.find_resources("AWS::IAM::Policy"))


def test_api_has_observability_dashboard():
    _synth_all()["api"].resource_count_is("AWS::CloudWatch::Dashboard", 1)


def test_no_wildcard_actions_on_any_stack():
    """Rubric: no bare `*` IAM actions ANYWHERE — covers all 7 stacks, not just Api.

    Resource wildcards (resources=["*"]) are intentionally allowed for the few
    actions that have no resource-level scoping (pricing:GetProducts, the
    AgentCore control-plane provider, the generated-stack CloudFormation preview
    role) and are reviewed in agent_stack/validation_stack; this guards the
    rubric's hard line, which is wildcard *actions*.
    """
    for name, template in _synth_all().items():
        for stmt in _all_policy_statements(template):
            action = stmt.get("Action")
            actions = action if isinstance(action, list) else [action]
            assert "*" not in actions, f"wildcard action in {name} stack: {stmt}"
