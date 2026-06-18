"""Storage primitives: S3 bucket, DynamoDB table, custom EventBridge bus.

Generic — the team should rename and remodel based on the chosen use case.
DynamoDB schema is intentionally minimal (pk/sk). Add GSIs based on access patterns.
"""
from aws_cdk import RemovalPolicy, Stack
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_events as events
from aws_cdk import aws_s3 as s3
from constructs import Construct


class StorageStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.data_bucket = s3.Bucket(
            self,
            "DataBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            versioned=True,
            event_bridge_enabled=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        self.data_table = dynamodb.TableV2(
            self,
            "DataTable",
            partition_key=dynamodb.Attribute(name="pk", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="sk", type=dynamodb.AttributeType.STRING),
            billing=dynamodb.Billing.on_demand(),
            encryption=dynamodb.TableEncryptionV2.aws_managed_key(),
            time_to_live_attribute="ttl",
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True,
            ),
            removal_policy=RemovalPolicy.DESTROY,
        )

        self.event_bus = events.EventBus(self, "AppEventBus")
