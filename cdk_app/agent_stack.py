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

        # Bedrock model invocation — scope to a specific model family if known
        execution_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                resources=[
                    f"arn:aws:bedrock:{self.region}::foundation-model/anthropic.claude-*",
                ],
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

        # Register the AgentCore runtime via the control-plane API.
        # The team can adjust agentRuntimeName / protocolConfiguration to taste.
        runtime_name = "lab3_agent"
        create_runtime = cr.AwsCustomResource(
            self,
            "CreateAgentRuntime",
            on_create=cr.AwsSdkCall(
                service="bedrock-agentcore-control",
                action="CreateAgentRuntime",
                parameters={
                    "agentRuntimeName": runtime_name,
                    "agentRuntimeArtifact": {
                        "containerConfiguration": {
                            "containerUri": image.image_uri,
                        },
                    },
                    "roleArn": execution_role.role_arn,
                    "networkConfiguration": {"networkMode": "PUBLIC"},
                    "environmentVariables": {
                        "DATA_TABLE_NAME": data_table.table_name,
                        "EVENT_BUS_NAME": event_bus.event_bus_name,
                        "DATA_BUCKET_NAME": data_bucket.bucket_name,
                        "VALIDATION_PROJECT_NAME": validation_project.project_name,
                        "CFN_EXECUTION_ROLE_ARN": cloudformation_execution_role.role_arn,
                    },
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
