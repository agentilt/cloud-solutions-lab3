"""Static frontend hosting and deployment for CloudCompass Builder."""
from pathlib import Path

from aws_cdk import Aws, CfnOutput, Fn, RemovalPolicy, Stack
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3_deployment
from constructs import Construct

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


class FrontendHostingStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.site_bucket = s3.Bucket(
            self,
            "SiteBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            versioned=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        origin_access_control = cloudfront.CfnOriginAccessControl(
            self,
            "OriginAccessControl",
            origin_access_control_config=cloudfront.CfnOriginAccessControl.OriginAccessControlConfigProperty(
                name=f"{self.stack_name}-oac",
                origin_access_control_origin_type="s3",
                signing_behavior="always",
                signing_protocol="sigv4",
            ),
        )

        self.distribution = cloudfront.CfnDistribution(
            self,
            "Distribution",
            distribution_config=cloudfront.CfnDistribution.DistributionConfigProperty(
                enabled=True,
                default_root_object="index.html",
                origins=[
                    cloudfront.CfnDistribution.OriginProperty(
                        id="SiteBucketOrigin",
                        domain_name=self.site_bucket.bucket_regional_domain_name,
                        origin_access_control_id=origin_access_control.attr_id,
                        s3_origin_config=cloudfront.CfnDistribution.S3OriginConfigProperty(
                            origin_access_identity="",
                        ),
                    )
                ],
                default_cache_behavior=cloudfront.CfnDistribution.DefaultCacheBehaviorProperty(
                    target_origin_id="SiteBucketOrigin",
                    viewer_protocol_policy="redirect-to-https",
                    allowed_methods=["GET", "HEAD", "OPTIONS"],
                    cached_methods=["GET", "HEAD", "OPTIONS"],
                    compress=True,
                    forwarded_values=cloudfront.CfnDistribution.ForwardedValuesProperty(
                        query_string=False,
                        cookies=cloudfront.CfnDistribution.CookiesProperty(forward="none"),
                    ),
                ),
                custom_error_responses=[
                    cloudfront.CfnDistribution.CustomErrorResponseProperty(
                        error_code=403,
                        response_code=200,
                        response_page_path="/index.html",
                    ),
                    cloudfront.CfnDistribution.CustomErrorResponseProperty(
                        error_code=404,
                        response_code=200,
                        response_page_path="/index.html",
                    ),
                ],
                price_class="PriceClass_100",
                http_version="http2and3",
                ipv6_enabled=True,
            ),
        )

        self.site_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject"],
                resources=[self.site_bucket.arn_for_objects("*")],
                principals=[iam.ServicePrincipal("cloudfront.amazonaws.com")],
                conditions={
                    "StringEquals": {
                        "AWS:SourceArn": Fn.sub(
                            "arn:${AWS::Partition}:cloudfront::${AWS::AccountId}:distribution/${DistributionId}",
                            {"DistributionId": self.distribution.ref},
                        )
                    }
                },
            )
        )

        self.frontend_url = f"https://{self.distribution.attr_domain_name}/"

        CfnOutput(self, "FrontendUrl", value=self.frontend_url)
        CfnOutput(self, "FrontendBucketName", value=self.site_bucket.bucket_name)


class FrontendDeploymentStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        site_bucket: s3.IBucket,
        distribution: cloudfront.CfnDistribution,
        api_url: str,
        user_pool: cognito.IUserPool,
        user_pool_client: cognito.IUserPoolClient,
        user_pool_domain_base_url: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        config_json = self.to_json_string(
            {
                "apiUrl": api_url,
                "region": Aws.REGION,
                "userPoolId": user_pool.user_pool_id,
                "userPoolClientId": user_pool_client.user_pool_client_id,
                "cognitoDomain": user_pool_domain_base_url,
                "redirectUri": f"https://{distribution.attr_domain_name}/",
            }
        )

        s3_deployment.BucketDeployment(
            self,
            "FrontendDeployment",
            sources=[
                s3_deployment.Source.asset(str(FRONTEND_DIR)),
                s3_deployment.Source.data("config.json", config_json),
            ],
            destination_bucket=site_bucket,
            retain_on_delete=False,
        )
