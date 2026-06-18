"""Validation and CloudFormation preview resources."""
from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_codebuild as codebuild
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from constructs import Construct


class ValidationStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        artifact_bucket: s3.IBucket,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        log_group = logs.LogGroup(
            self,
            "ValidationLogGroup",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )

        self.validation_project = codebuild.Project(
            self,
            "ValidationProject",
            description="Validates generated CloudCompass CDK projects before change-set preview.",
            timeout=Duration.minutes(15),
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                compute_type=codebuild.ComputeType.SMALL,
            ),
            logging=codebuild.LoggingOptions(
                cloud_watch=codebuild.CloudWatchLoggingOptions(log_group=log_group)
            ),
            build_spec=codebuild.BuildSpec.from_object(
                {
                    "version": "0.2",
                    "phases": {
                        "install": {
                            "runtime-versions": {"python": "3.12", "nodejs": "20"},
                            "commands": [
                                "python -m pip install --upgrade pip",
                                "npm install -g aws-cdk@latest",
                            ],
                        },
                        "build": {
                            "commands": [
                                "test -n \"$ARTIFACT_S3_URI\"",
                                "aws s3 cp \"$ARTIFACT_S3_URI\" /tmp/cdk-project.zip",
                                "mkdir -p /tmp/generated",
                                "python -m zipfile -e /tmp/cdk-project.zip /tmp/generated",
                                "cd /tmp/generated",
                                "python -m pip install -r requirements.txt",
                                "python -m compileall .",
                                "cdk synth",
                            ]
                        },
                    },
                }
            ),
        )
        artifact_bucket.grant_read(self.validation_project)

        self.cloudformation_execution_role = iam.Role(
            self,
            "GeneratedChangeSetExecutionRole",
            assumed_by=iam.ServicePrincipal("cloudformation.amazonaws.com"),
            description="Execution role used only to preview generated CloudCompass change sets.",
        )
        self.cloudformation_execution_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "apigateway:DELETE",
                    "apigateway:GET",
                    "apigateway:PATCH",
                    "apigateway:POST",
                    "apigateway:PUT",
                    "apigatewayv2:CreateApi",
                    "apigatewayv2:CreateIntegration",
                    "apigatewayv2:CreateRoute",
                    "apigatewayv2:DeleteApi",
                    "apigatewayv2:DeleteIntegration",
                    "apigatewayv2:DeleteRoute",
                    "apigatewayv2:GetApi",
                    "apigatewayv2:GetIntegration",
                    "apigatewayv2:GetRoute",
                    "apigatewayv2:UpdateApi",
                    "apigatewayv2:UpdateIntegration",
                    "apigatewayv2:UpdateRoute",
                    "cloudformation:CreateChangeSet",
                    "cloudformation:DeleteChangeSet",
                    "cloudformation:DescribeChangeSet",
                    "cloudformation:DescribeStacks",
                    "cloudformation:ExecuteChangeSet",
                    "dynamodb:CreateTable",
                    "dynamodb:DeleteTable",
                    "dynamodb:DescribeTable",
                    "dynamodb:TagResource",
                    "dynamodb:UpdateContinuousBackups",
                    "dynamodb:UpdateTable",
                    "iam:AttachRolePolicy",
                    "iam:CreatePolicy",
                    "iam:CreateRole",
                    "iam:DeletePolicy",
                    "iam:DeleteRole",
                    "iam:DeleteRolePolicy",
                    "iam:DetachRolePolicy",
                    "iam:GetPolicy",
                    "iam:GetRole",
                    "iam:PassRole",
                    "iam:PutRolePolicy",
                    "iam:TagRole",
                    "lambda:AddPermission",
                    "lambda:CreateFunction",
                    "lambda:DeleteFunction",
                    "lambda:GetFunction",
                    "lambda:TagResource",
                    "lambda:UpdateFunctionCode",
                    "lambda:UpdateFunctionConfiguration",
                    "logs:CreateLogGroup",
                    "logs:DeleteLogGroup",
                    "logs:PutRetentionPolicy",
                    "s3:CreateBucket",
                    "s3:DeleteBucket",
                    "s3:GetBucketLocation",
                    "s3:GetBucketPolicy",
                    "s3:PutBucketEncryption",
                    "s3:PutBucketPolicy",
                    "s3:PutBucketPublicAccessBlock",
                    "s3:PutBucketVersioning",
                    "s3:PutEncryptionConfiguration",
                    "s3:PutLifecycleConfiguration",
                    "s3:PutTagging",
                ],
                resources=["*"],
            )
        )

        CfnOutput(self, "ValidationProjectName", value=self.validation_project.project_name)
        CfnOutput(
            self,
            "ChangeSetExecutionRoleArn",
            value=self.cloudformation_execution_role.role_arn,
        )
