"""Authenticated HTTP API and Lambda entry points."""
from pathlib import Path

from aws_cdk import CfnOutput, Duration, Stack
from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk import aws_apigatewayv2_authorizers as apigwv2_auth
from aws_cdk import aws_apigatewayv2_integrations as apigwv2_integ
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
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
        data_table: dynamodb.ITableV2,
        user_pool: cognito.IUserPool,
        user_pool_client: cognito.IUserPoolClient,
        agent_runtime_arn: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        common_lambda_kwargs = dict(
            runtime=lambda_.Runtime.PYTHON_3_13,
            architecture=lambda_.Architecture.ARM_64,
            timeout=Duration.seconds(60),
            memory_size=512,
            tracing=lambda_.Tracing.ACTIVE,
            log_retention=logs.RetentionDays.ONE_MONTH,
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

        project_fn = lambda_.Function(
            self,
            "ProjectFn",
            code=lambda_.Code.from_asset(str(LAMBDA_DIR / "projects")),
            handler="handler.handler",
            environment={
                "AGENT_RUNTIME_ARN": agent_runtime_arn,
                "DATA_BUCKET_NAME": data_bucket.bucket_name,
                "DATA_TABLE_NAME": data_table.table_name,
            },
            **common_lambda_kwargs,
        )
        data_table.grant_read_write_data(project_fn)
        data_bucket.grant_read(project_fn)
        project_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock-agentcore:InvokeAgentRuntime"],
                resources=[agent_runtime_arn],
            )
        )

        http_api = apigwv2.HttpApi(
            self,
            "HttpApi",
            cors_preflight=apigwv2.CorsPreflightOptions(
                allow_methods=[
                    apigwv2.CorsHttpMethod.GET,
                    apigwv2.CorsHttpMethod.POST,
                    apigwv2.CorsHttpMethod.OPTIONS,
                ],
                allow_origins=["*"],
                allow_headers=["authorization", "content-type"],
            ),
        )

        authorizer = apigwv2_auth.HttpJwtAuthorizer(
            "CognitoJwtAuthorizer",
            jwt_issuer=f"https://cognito-idp.{self.region}.amazonaws.com/{user_pool.user_pool_id}",
            jwt_audience=[user_pool_client.user_pool_client_id],
        )

        def add_protected_route(
            path: str,
            method: apigwv2.HttpMethod,
            integration: apigwv2_integ.HttpLambdaIntegration,
        ) -> None:
            http_api.add_routes(
                path=path,
                methods=[method],
                integration=integration,
                authorizer=authorizer,
            )

        project_integration = apigwv2_integ.HttpLambdaIntegration(
            "ProjectIntegration", project_fn
        )
        add_protected_route("/projects", apigwv2.HttpMethod.POST, project_integration)
        add_protected_route(
            "/projects/{project_id}", apigwv2.HttpMethod.GET, project_integration
        )
        add_protected_route(
            "/upload-url",
            apigwv2.HttpMethod.POST,
            apigwv2_integ.HttpLambdaIntegration("UploadUrlIntegration", upload_url_fn),
        )
        add_protected_route(
            "/invoke",
            apigwv2.HttpMethod.POST,
            apigwv2_integ.HttpLambdaIntegration("AgentInvokerIntegration", agent_invoker_fn),
        )

        self.http_api = http_api

        # Observability: a CloudWatch dashboard over the request tier. Combined with
        # X-Ray active tracing (above) and one-month log retention, this is the
        # operational view for the API + agent-invoker path. AgentCore runtime
        # traces/metrics are emitted to CloudWatch by the platform.
        functions = {
            "project": project_fn,
            "agent_invoker": agent_invoker_fn,
            "upload_url": upload_url_fn,
        }
        dashboard = cloudwatch.Dashboard(self, "ObservabilityDashboard")
        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Lambda invocations",
                left=[fn.metric_invocations() for fn in functions.values()],
                width=12,
            ),
            cloudwatch.GraphWidget(
                title="Lambda errors",
                left=[fn.metric_errors() for fn in functions.values()],
                width=12,
            ),
            cloudwatch.GraphWidget(
                title="Lambda duration (p95)",
                left=[fn.metric_duration(statistic="p95") for fn in functions.values()],
                width=12,
            ),
        )

        CfnOutput(self, "ApiUrl", value=http_api.url or "")
        CfnOutput(self, "DashboardName", value=dashboard.dashboard_name)
