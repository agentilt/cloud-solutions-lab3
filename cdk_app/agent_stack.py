"""Bedrock AgentCore runtime + ECR image + IAM execution role.

Flow:
  1. DockerImageAsset builds + pushes the ARM64 agent image to ECR.
  2. IAM execution role grants the runtime least-privilege access to:
       - invoke Bedrock foundation models
       - read/write the app DynamoDB table
       - put events on the app EventBridge bus
       - read from the data S3 bucket
  3. AwsCustomResource calls bedrock-agentcore-control:CreateAgentRuntime to
     register the runtime, and exposes the runtime ARN as `self.runtime_arn`.

Notes:
  - AgentCore L2 CDK constructs do not exist yet in mainline aws-cdk-lib. If/when
    they ship, replace the AwsCustomResource block with the native construct.
  - The boto3 call shape (CreateAgentRuntime) may evolve. If a deploy fails on
    that call, check the latest bedrock-agentcore-control API reference.
"""
from pathlib import Path

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_codebuild as codebuild
from aws_cdk import aws_ecr_assets as ecr_assets
from aws_cdk import aws_events as events
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import custom_resources as cr
from constructs import Construct

AGENT_DIR = Path(__file__).resolve().parent.parent / "agent"


class AgentStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        data_table: dynamodb.ITableV2,
        event_bus: events.IEventBus,
        data_bucket: s3.IBucket,
        validation_project: codebuild.IProject,
        cloudformation_execution_role: iam.IRole,
        knowledge_base_id: str,
        knowledge_base_arn: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        image = ecr_assets.DockerImageAsset(
            self,
            "AgentImage",
            directory=str(AGENT_DIR.parent),
            file="agent/Dockerfile",
            platform=ecr_assets.Platform.LINUX_ARM64,
        )

        execution_role = iam.Role(
            self,
            "AgentExecutionRole",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            description="Execution role for the Strands Agent on Bedrock AgentCore",
        )

        # Pull the agent image from ECR
        image.repository.grant_pull(execution_role)

        # Bedrock model invocation. Strands' default is a Sonnet-class *inference
        # profile* (e.g. us.anthropic.claude-sonnet-4-6); Haiku is used for cheap
        # subtasks when BEDROCK_FAST_MODEL_ID is set. Invoking via an inference
        # profile requires permission on BOTH the profile ARN and the underlying
        # foundation-model ARNs across the regions the profile routes to.
        execution_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                resources=[
                    # Foundation models (region-agnostic; profiles route cross-region).
                    f"arn:{self.partition}:bedrock:*::foundation-model/anthropic.claude-*",
                    # Cross-region / application inference profiles in this account.
                    f"arn:{self.partition}:bedrock:{self.region}:{self.account}"
                    ":inference-profile/*.anthropic.claude-*",
                ],
            )
        )

        # RAG: retrieve approved guidance from the Bedrock Knowledge Base.
        execution_role.add_to_policy(
            iam.PolicyStatement(actions=["bedrock:Retrieve"], resources=[knowledge_base_arn])
        )

        # Bedrock Guardrail: prompt-injection + content safety on the orchestrator.
        # agent/agent.py attaches it to every model call via BEDROCK_GUARDRAIL_ID.
        guardrail = bedrock.CfnGuardrail(
            self,
            "AgentGuardrail",
            name=f"cloudcompass-{self.node.addr[:8]}",
            description="Prompt-injection + content safety for the CloudCompass orchestrator.",
            blocked_input_messaging="Your request was blocked by CloudCompass safety guardrails.",
            blocked_outputs_messaging="The response was blocked by CloudCompass safety guardrails.",
            content_policy_config=bedrock.CfnGuardrail.ContentPolicyConfigProperty(
                filters_config=[
                    # PROMPT_ATTACK is input-only (output_strength must be NONE).
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="PROMPT_ATTACK", input_strength="HIGH", output_strength="NONE"
                    ),
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="HATE", input_strength="HIGH", output_strength="HIGH"
                    ),
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="VIOLENCE", input_strength="MEDIUM", output_strength="MEDIUM"
                    ),
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="MISCONDUCT", input_strength="MEDIUM", output_strength="MEDIUM"
                    ),
                ],
            ),
        )
        execution_role.add_to_policy(
            iam.PolicyStatement(
                actions=["bedrock:ApplyGuardrail"], resources=[guardrail.attr_guardrail_arn]
            )
        )

        # App data access (tight)
        data_table.grant_read_write_data(execution_role)
        data_bucket.grant_read_write(execution_role)
        event_bus.grant_put_events_to(execution_role)
        execution_role.add_to_policy(
            iam.PolicyStatement(
                actions=["codebuild:StartBuild", "codebuild:BatchGetBuilds"],
                resources=[validation_project.project_arn],
            )
        )
        cloudformation_execution_role.grant_pass_role(execution_role)
        execution_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "cloudformation:CreateChangeSet",
                    "cloudformation:DeleteChangeSet",
                    "cloudformation:DescribeChangeSet",
                    "cloudformation:DescribeStacks",
                    "cloudformation:ValidateTemplate",
                ],
                resources=[
                    f"arn:aws:cloudformation:{self.region}:{self.account}:stack/CloudCompassGenerated-*/*",
                    f"arn:aws:cloudformation:{self.region}:{self.account}:changeSet/CloudCompassGenerated-*/*",
                ],
            )
        )
        execution_role.add_to_policy(
            iam.PolicyStatement(actions=["pricing:GetProducts"], resources=["*"])
        )

        # CloudWatch logs for the runtime
        log_group = logs.LogGroup(
            self,
            "AgentLogGroup",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )
        log_group.grant_write(execution_role)

        # Register the AgentCore runtime via the control-plane API. No AgentCore L2
        # construct exists yet, so we drive bedrock-agentcore-control directly.
        #   - install_latest_aws_sdk=True: the control-plane API is newer than the
        #     boto3 bundled into the custom-resource Lambda, so we must fetch it.
        #   - unique-per-stack name: CreateAgentRuntime requires a unique name; a
        #     fixed "lab3_agent" collides on any second deploy in the account/region.
        #   - on_update (UpdateAgentRuntime): without it, AwsCustomResource replays
        #     on_create for updates and CreateAgentRuntime fails on the existing name,
        #     so changed agent code would never roll out. The image_uri carries the
        #     asset hash, so a code change flips the update call and ships the new
        #     container as a new runtime version.
        runtime_name = f"cloudcompass_{self.node.addr[:8]}"

        # One source of truth shared by create + update so they cannot drift.
        agent_artifact = {"containerConfiguration": {"containerUri": image.image_uri}}
        network_configuration = {"networkMode": "PUBLIC"}
        protocol_configuration = {"serverProtocol": "HTTP"}  # BedrockAgentCoreApp serves HTTP/8080
        environment_variables = {
            "DATA_TABLE_NAME": data_table.table_name,
            "EVENT_BUS_NAME": event_bus.event_bus_name,
            "DATA_BUCKET_NAME": data_bucket.bucket_name,
            "VALIDATION_PROJECT_NAME": validation_project.project_name,
            "CFN_EXECUTION_ROLE_ARN": cloudformation_execution_role.role_arn,
            "KNOWLEDGE_BASE_ID": knowledge_base_id,
            "BEDROCK_GUARDRAIL_ID": guardrail.attr_guardrail_id,
            "BEDROCK_GUARDRAIL_VERSION": "DRAFT",
        }

        create_runtime = cr.AwsCustomResource(
            self,
            "CreateAgentRuntime",
            install_latest_aws_sdk=True,
            on_create=cr.AwsSdkCall(
                service="bedrock-agentcore-control",
                action="CreateAgentRuntime",
                parameters={
                    "agentRuntimeName": runtime_name,
                    "agentRuntimeArtifact": agent_artifact,
                    "roleArn": execution_role.role_arn,
                    "networkConfiguration": network_configuration,
                    "protocolConfiguration": protocol_configuration,
                    "environmentVariables": environment_variables,
                },
                physical_resource_id=cr.PhysicalResourceId.from_response("agentRuntimeId"),
            ),
            on_update=cr.AwsSdkCall(
                service="bedrock-agentcore-control",
                action="UpdateAgentRuntime",
                parameters={
                    "agentRuntimeId": cr.PhysicalResourceIdReference(),
                    "agentRuntimeArtifact": agent_artifact,
                    "roleArn": execution_role.role_arn,
                    "networkConfiguration": network_configuration,
                    "protocolConfiguration": protocol_configuration,
                    "environmentVariables": environment_variables,
                },
                physical_resource_id=cr.PhysicalResourceId.from_response("agentRuntimeId"),
            ),
            on_delete=cr.AwsSdkCall(
                service="bedrock-agentcore-control",
                action="DeleteAgentRuntime",
                parameters={"agentRuntimeId": cr.PhysicalResourceIdReference()},
            ),
            policy=cr.AwsCustomResourcePolicy.from_statements(
                [
                    iam.PolicyStatement(
                        actions=[
                            "bedrock-agentcore:CreateAgentRuntime",
                            "bedrock-agentcore:DeleteAgentRuntime",
                            "bedrock-agentcore:UpdateAgentRuntime",
                            "bedrock-agentcore:GetAgentRuntime",
                        ],
                        resources=["*"],
                    ),
                    iam.PolicyStatement(
                        actions=["iam:PassRole"],
                        resources=[execution_role.role_arn],
                    ),
                ]
            ),
            timeout=Duration.minutes(5),
        )
        create_runtime.node.add_dependency(image)

        self.runtime_arn = create_runtime.get_response_field("agentRuntimeArn")

        CfnOutput(self, "AgentRuntimeArn", value=self.runtime_arn)
        CfnOutput(self, "AgentImageUri", value=image.image_uri)
        CfnOutput(self, "AgentExecutionRoleArn", value=execution_role.role_arn)
