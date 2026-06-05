"""API Gateway HTTP API + Lambda entry points.

Routes (placeholders — adjust to the chosen use case):
  POST /upload-url   → upload_url Lambda  → presigned S3 PUT URL
  POST /invoke       → agent_invoker Lambda → InvokeAgentRuntime → JSON response
"""
from pathlib import Path

from aws_cdk import CfnOutput, Duration, Stack
from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk import aws_apigatewayv2_integrations as apigwv2_integ
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3 as s3
from constructs import Construct

LAMBDA_DIR = Path(__file__).resolve().parent.parent / "lambdas"


class ApiStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        data_bucket: s3.IBucket,
        agent_runtime_arn: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        common_lambda_kwargs = dict(
            runtime=lambda_.Runtime.PYTHON_3_13,
            architecture=lambda_.Architecture.ARM_64,
            timeout=Duration.seconds(30),
            memory_size=512,
            tracing=lambda_.Tracing.ACTIVE,
        )

        upload_url_fn = lambda_.Function(
            self,
            "UploadUrlFn",
            code=lambda_.Code.from_asset(str(LAMBDA_DIR / "upload_url")),
            handler="handler.handler",
            environment={"DATA_BUCKET_NAME": data_bucket.bucket_name},
            **common_lambda_kwargs,
        )
        data_bucket.grant_put(upload_url_fn)

        agent_invoker_fn = lambda_.Function(
            self,
            "AgentInvokerFn",
            code=lambda_.Code.from_asset(str(LAMBDA_DIR / "agent_invoker")),
            handler="handler.handler",
            environment={"AGENT_RUNTIME_ARN": agent_runtime_arn},
            **common_lambda_kwargs,
        )
        agent_invoker_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock-agentcore:InvokeAgentRuntime"],
                resources=[agent_runtime_arn],
            )
        )

        http_api = apigwv2.HttpApi(
            self,
            "HttpApi",
            cors_preflight=apigwv2.CorsPreflightOptions(
                allow_methods=[apigwv2.CorsHttpMethod.POST, apigwv2.CorsHttpMethod.OPTIONS],
                allow_origins=["*"],  # tighten for production
                allow_headers=["content-type"],
            ),
        )

        http_api.add_routes(
            path="/upload-url",
            methods=[apigwv2.HttpMethod.POST],
            integration=apigwv2_integ.HttpLambdaIntegration(
                "UploadUrlIntegration", upload_url_fn
            ),
        )
        http_api.add_routes(
            path="/invoke",
            methods=[apigwv2.HttpMethod.POST],
            integration=apigwv2_integ.HttpLambdaIntegration(
                "AgentInvokerIntegration", agent_invoker_fn
            ),
        )

        CfnOutput(self, "ApiUrl", value=http_api.url or "")
