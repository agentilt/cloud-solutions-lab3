"""Basic CDK assertions to keep the stacks honest.

These don't deploy — they just synth and inspect the CloudFormation output.
"""
import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

from cdk_app.agent_stack import AgentStack
from cdk_app.api_stack import ApiStack
from cdk_app.storage_stack import StorageStack


def _synth_all():
    app = cdk.App()
    storage = StorageStack(app, "TestStorage")
    agent = AgentStack(
        app,
        "TestAgent",
        data_table=storage.data_table,
        event_bus=storage.event_bus,
        data_bucket=storage.data_bucket,
    )
    api = ApiStack(
        app,
        "TestApi",
        data_bucket=storage.data_bucket,
        agent_runtime_arn=agent.runtime_arn,
    )
    return (
        Template.from_stack(storage),
        Template.from_stack(agent),
        Template.from_stack(api),
    )


def test_storage_has_encrypted_bucket():
    storage, _agent, _api = _synth_all()
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


def test_storage_dynamodb_has_pk_sk():
    storage, _agent, _api = _synth_all()
    storage.has_resource_properties(
        "AWS::DynamoDB::GlobalTable",
        Match.object_like(
            {
                "KeySchema": [
                    {"AttributeName": "pk", "KeyType": "HASH"},
                    {"AttributeName": "sk", "KeyType": "RANGE"},
                ],
            }
        ),
    )


def test_api_has_two_routes():
    _storage, _agent, api = _synth_all()
    api.resource_count_is("AWS::ApiGatewayV2::Route", 2)


def test_no_wildcard_actions_on_lambda_roles():
    """Rubric: no `*` actions on IAM policies."""
    _storage, _agent, api = _synth_all()
    policies = api.find_resources("AWS::IAM::Policy")
    for _logical_id, policy in policies.items():
        for stmt in policy["Properties"]["PolicyDocument"]["Statement"]:
            action = stmt.get("Action")
            actions = action if isinstance(action, list) else [action]
            assert "*" not in actions, f"wildcard action found in {_logical_id}: {stmt}"
