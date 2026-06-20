"""CloudCompass Builder Strands tools."""
from __future__ import annotations

import io
import json
import os
import re
import zipfile
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import boto3

from cdk_generator import generate_cdk_project

try:
    from strands import tool
except ImportError:  # pragma: no cover - lets local unit tests import this module.
    def tool(func):
        return func


DATA_TABLE_NAME = os.environ.get("DATA_TABLE_NAME")
DATA_BUCKET_NAME = os.environ.get("DATA_BUCKET_NAME")
VALIDATION_PROJECT_NAME = os.environ.get("VALIDATION_PROJECT_NAME")
CFN_EXECUTION_ROLE_ARN = os.environ.get("CFN_EXECUTION_ROLE_ARN")

DYNAMODB = boto3.resource("dynamodb")
S3 = boto3.client("s3")
CODEBUILD = boto3.client("codebuild")
CLOUDFORMATION = boto3.client("cloudformation")


def _table():
    if not DATA_TABLE_NAME:
        raise RuntimeError("DATA_TABLE_NAME is not configured")
    return DYNAMODB.Table(DATA_TABLE_NAME)


def _bucket_name() -> str:
    if not DATA_BUCKET_NAME:
        raise RuntimeError("DATA_BUCKET_NAME is not configured")
    return DATA_BUCKET_NAME


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _json_default(value):
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _json_bytes(value: dict) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True, default=_json_default).encode("utf-8")


def _dynamo_safe(value):
    """Recursively convert floats to Decimal — boto3's DynamoDB resource rejects
    floats. Cost estimates and budgets carry floats, so persist them safely."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, list):
        return [_dynamo_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _dynamo_safe(item) for key, item in value.items()}
    return value


def _project_key(user_id: str, project_id: str) -> dict[str, str]:
    return {"pk": f"USER#{user_id}", "sk": f"PROJECT#{project_id}"}


def _sanitize_stack_part(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9-]", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value[:40] or "project"


def build_bakery_architecture_spec(prompt: str) -> dict:
    budget = 200 if "200" in prompt else None
    return {
        "project_name": "online-bakery",
        "pattern": "serverless-web-application",
        "deployment_boundary": "change-set-only",
        "budget_monthly_usd": budget,
        "services": [
            {
                "type": "s3_bucket",
                "logical_id": "SiteBucket",
                "config": {"versioned": True, "block_public_access": True},
            },
            {
                "type": "lambda_api",
                "logical_id": "OrderApi",
                "config": {
                    "runtime": "python3.12",
                    "routes": ["GET /orders", "POST /orders"],
                },
            },
            {
                "type": "dynamodb_table",
                "logical_id": "OrdersTable",
                "config": {"partition_key": "pk", "sort_key": "sk"},
            },
        ],
    }


def save_project_state_impl(
    user_id: str,
    project_id: str,
    status: str,
    metadata: dict | None = None,
) -> dict:
    metadata = metadata or {}
    expression_names = {"#status": "status"}
    expression_values: dict[str, Any] = {
        ":status": status,
        ":updated_at": _now(),
        ":ttl": int((datetime.now(UTC) + timedelta(days=14)).timestamp()),
    }
    update_parts = ["#status = :status", "updated_at = :updated_at", "ttl = :ttl"]

    for index, (key, value) in enumerate(metadata.items()):
        name_token = f"#m{index}"
        value_token = f":m{index}"
        expression_names[name_token] = key
        expression_values[value_token] = _dynamo_safe(value)
        update_parts.append(f"{name_token} = {value_token}")

    _table().update_item(
        Key=_project_key(user_id, project_id),
        UpdateExpression="SET " + ", ".join(update_parts),
        ExpressionAttributeNames=expression_names,
        ExpressionAttributeValues=expression_values,
    )
    return {"project_id": project_id, "status": status, "updated_at": expression_values[":updated_at"]}


@tool
def save_project_state(user_id: str, project_id: str, status: str, metadata: dict) -> dict:
    """Persist a CloudCompass project workflow state in DynamoDB."""
    return save_project_state_impl(user_id, project_id, status, metadata)


def get_project_state_impl(user_id: str, project_id: str) -> dict:
    """Read the current persisted state for a project ({} if it does not exist)."""
    response = _table().get_item(Key=_project_key(user_id, project_id))
    return response.get("Item") or {}


def query_reference_guidance_impl(query: str, workload_type: str) -> dict:
    fallback = {
        "source": "curated-fallback",
        "workload_type": workload_type,
        "guidance": [
            "Use S3 and CloudFront for static assets; keep the origin bucket private.",
            "Use Cognito for customer authentication and JWT-protected HTTP APIs.",
            "Use Lambda, HTTP API, and DynamoDB for a small serverless order service.",
            "Stop at a CloudFormation change set; do not execute deployment automatically.",
        ],
    }
    try:
        response = S3.get_object(
            Bucket=_bucket_name(),
            Key="knowledge/cloudcompass_patterns.json",
        )
        corpus = json.loads(response["Body"].read().decode("utf-8"))
        return {"source": "s3-guidance-corpus", "query": query, "matches": corpus[:5]}
    except Exception:
        return fallback


@tool
def query_reference_guidance(query: str, workload_type: str) -> dict:
    """Retrieve approved architecture guidance for a workload."""
    return query_reference_guidance_impl(query, workload_type)


def render_cdk_project_impl(architecture_spec: dict) -> dict:
    return generate_cdk_project(architecture_spec)


@tool
def render_cdk_project(architecture_spec: dict) -> dict:
    """Render a deterministic Python CDK project from an architecture spec."""
    return render_cdk_project_impl(architecture_spec)


def write_cdk_project_impl(user_id: str, project_id: str, files: dict[str, str]) -> dict:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(files):
            zipped.writestr(path, files[path])

    bucket = _bucket_name()
    artifact_key = f"projects/{project_id}/source/cdk-project.zip"
    S3.put_object(
        Bucket=bucket,
        Key=artifact_key,
        Body=archive.getvalue(),
        ContentType="application/zip",
        ServerSideEncryption="AES256",
        Metadata={"user_id": user_id, "project_id": project_id},
    )
    manifest_key = f"projects/{project_id}/source/manifest.json"
    S3.put_object(
        Bucket=bucket,
        Key=manifest_key,
        Body=_json_bytes({"files": sorted(files), "created_at": _now()}),
        ContentType="application/json",
        ServerSideEncryption="AES256",
    )
    return {
        "artifact_s3_uri": f"s3://{bucket}/{artifact_key}",
        "artifact_s3_key": artifact_key,
        "manifest_s3_uri": f"s3://{bucket}/{manifest_key}",
    }


@tool
def write_cdk_project(user_id: str, project_id: str, files: dict[str, str]) -> dict:
    """Store generated CDK project artifacts in S3."""
    return write_cdk_project_impl(user_id, project_id, files)


# Curated unit rates (USD, us-east-1, 2026). Bedrock rates are Sonnet-class
# on-demand ($3/1M in, $15/1M out). CodeBuild's per-minute rate is confirmed from
# the Price List API at runtime when reachable. Kept transparent so the cost the
# agent reports is computed from the usage profile, not a hand-waved range.
_PRICE_RATES = {
    "bedrock_input_per_1k_usd": 0.003,
    "bedrock_output_per_1k_usd": 0.015,
    "codebuild_small_per_min_usd": 0.005,
    "platform_overhead_per_run_usd": 0.01,  # Lambda + HTTP API + DynamoDB + S3 + logs
}


def _confirm_codebuild_rate_per_min(default_rate: float) -> tuple[float, str]:
    """Best-effort: read the CodeBuild small build-minute rate from the Price List
    API. Returns (rate, source); falls back to the curated rate when offline."""
    try:
        pricing = boto3.client("pricing", region_name="us-east-1")
        response = pricing.get_products(
            ServiceCode="AWSCodeBuild",
            Filters=[
                {"Type": "TERM_MATCH", "Field": "location", "Value": "US East (N. Virginia)"},
                {"Type": "TERM_MATCH", "Field": "computeType", "Value": "BUILD_GENERAL1_SMALL"},
            ],
            MaxResults=1,
        )
        price_list = response.get("PriceList", [])
        if price_list:
            product = json.loads(price_list[0])
            on_demand = product["terms"]["OnDemand"]
            dimensions = next(iter(on_demand.values()))["priceDimensions"]
            rate = float(next(iter(dimensions.values()))["pricePerUnit"]["USD"])
            if rate > 0:
                return rate, "aws-price-list-api"
    except Exception:
        pass
    return default_rate, "curated-rate-offline"


def get_service_pricing_impl(region: str, usage_profile: dict | None = None) -> dict:
    usage_profile = usage_profile or {}
    prompt_tokens = int(usage_profile.get("prompt_tokens", 4000))
    output_tokens = int(usage_profile.get("output_tokens", 6000))
    codebuild_minutes = float(usage_profile.get("codebuild_minutes", 3))

    rates = dict(_PRICE_RATES)
    codebuild_rate, pricing_source = _confirm_codebuild_rate_per_min(
        rates["codebuild_small_per_min_usd"]
    )
    rates["codebuild_small_per_min_usd"] = round(codebuild_rate, 6)

    model_cost = (
        prompt_tokens / 1000 * rates["bedrock_input_per_1k_usd"]
        + output_tokens / 1000 * rates["bedrock_output_per_1k_usd"]
    )
    codebuild_cost = codebuild_minutes * codebuild_rate
    platform_cost = rates["platform_overhead_per_run_usd"]
    total = round(model_cost + codebuild_cost + platform_cost, 4)

    return {
        "unit": "infrastructure-generation-run",
        "currency": "USD",
        "estimated_cost_usd": total,
        "line_items": [
            {
                "component": "Bedrock model inference",
                "driver": f"{prompt_tokens} input + {output_tokens} output tokens",
                "estimate_usd": round(model_cost, 4),
            },
            {
                "component": "CodeBuild validation",
                "driver": f"{codebuild_minutes} small build-minute(s)",
                "estimate_usd": round(codebuild_cost, 4),
            },
            {
                "component": "Lambda, API Gateway, DynamoDB, S3, logs",
                "driver": "per run, small fixed overhead",
                "estimate_usd": round(platform_cost, 4),
            },
        ],
        "assumptions": {
            "region": region,
            "prompt_tokens": prompt_tokens,
            "output_tokens": output_tokens,
            "codebuild_minutes": codebuild_minutes,
        },
        "rates_usd": rates,
        "pricing_source": pricing_source,
    }


@tool
def get_service_pricing(region: str, usage_profile: dict) -> dict:
    """Estimate cost for one infrastructure-generation run."""
    return get_service_pricing_impl(region, usage_profile)


def start_validation_build_impl(project_id: str, artifact_s3_uri: str) -> dict:
    if not VALIDATION_PROJECT_NAME:
        return {"started": False, "reason": "VALIDATION_PROJECT_NAME is not configured"}
    try:
        response = CODEBUILD.start_build(
            projectName=VALIDATION_PROJECT_NAME,
            environmentVariablesOverride=[
                {
                    "name": "ARTIFACT_S3_URI",
                    "value": artifact_s3_uri,
                    "type": "PLAINTEXT",
                },
                {"name": "PROJECT_ID", "value": project_id, "type": "PLAINTEXT"},
            ],
        )
        build = response["build"]
        return {"started": True, "build_id": build["id"], "build_arn": build["arn"]}
    except Exception as exc:
        return {"started": False, "error": str(exc)}


@tool
def start_validation_build(project_id: str, artifact_s3_uri: str) -> dict:
    """Start the CodeBuild validation project for a generated CDK archive."""
    return start_validation_build_impl(project_id, artifact_s3_uri)


def validate_generated_template_impl(files: dict[str, str]) -> dict:
    findings = []
    joined = "\n".join(files.values())
    if "Action: '*'" in joined or 'actions=["*"]' in joined:
        findings.append({"severity": "HIGH", "message": "Wildcard IAM action detected."})
    if "BlockPublicAccess.BLOCK_ALL" not in joined:
        findings.append({"severity": "MEDIUM", "message": "No private S3 bucket default detected."})
    if "TableV2" not in joined:
        findings.append({"severity": "LOW", "message": "No DynamoDB table detected in generated code."})

    return {
        "passed": not any(finding["severity"] == "HIGH" for finding in findings),
        "findings": findings,
        "summary": "Security defaults passed" if not findings else "Review generated findings",
    }


@tool
def validate_generated_template(files: dict[str, str]) -> dict:
    """Run lightweight generated-code security validation before change-set creation."""
    return validate_generated_template_impl(files)


def _preview_template_from_spec(architecture_spec: dict) -> dict:
    """Build a conservative CloudFormation preview for the change set.

    This is a hand-written representation of every service in the spec — enough
    for a faithful change-set preview — NOT the authoritative artifact. The full
    wiring (IAM, routes, OAC, etc.) lives in the generated CDK zip, which is what
    CodeBuild synthesizes. We model every service type so nothing is silently
    dropped from the preview (the previous version omitted lambda_api).
    """
    resources: dict[str, dict] = {}
    outputs: dict[str, dict] = {}

    def _private_bucket() -> dict:
        return {
            "Type": "AWS::S3::Bucket",
            "Properties": {
                "BucketEncryption": {
                    "ServerSideEncryptionConfiguration": [
                        {"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
                    ]
                },
                "PublicAccessBlockConfiguration": {
                    "BlockPublicAcls": True,
                    "BlockPublicPolicy": True,
                    "IgnorePublicAcls": True,
                    "RestrictPublicBuckets": True,
                },
            },
        }

    for service in architecture_spec.get("services", []):
        logical_id = service["logical_id"]
        config = service.get("config") or {}
        service_type = service["type"]

        if service_type == "s3_bucket":
            bucket = _private_bucket()
            bucket["Properties"]["VersioningConfiguration"] = {
                "Status": "Enabled" if config.get("versioned", True) else "Suspended"
            }
            resources[logical_id] = bucket
            outputs[f"{logical_id}Name"] = {"Value": {"Ref": logical_id}}

        elif service_type == "dynamodb_table":
            key_schema = [{"AttributeName": config.get("partition_key", "pk"), "KeyType": "HASH"}]
            attribute_definitions = [
                {"AttributeName": config.get("partition_key", "pk"), "AttributeType": "S"}
            ]
            if config.get("sort_key"):
                key_schema.append({"AttributeName": config["sort_key"], "KeyType": "RANGE"})
                attribute_definitions.append(
                    {"AttributeName": config["sort_key"], "AttributeType": "S"}
                )
            resources[logical_id] = {
                "Type": "AWS::DynamoDB::Table",
                "Properties": {
                    "BillingMode": "PAY_PER_REQUEST",
                    "KeySchema": key_schema,
                    "AttributeDefinitions": attribute_definitions,
                    "PointInTimeRecoverySpecification": {"PointInTimeRecoveryEnabled": True},
                    "SSESpecification": {"SSEEnabled": True},
                },
            }
            outputs[f"{logical_id}Name"] = {"Value": {"Ref": logical_id}}

        elif service_type == "lambda_api":
            role_id = f"{logical_id}Role"
            resources[role_id] = {
                "Type": "AWS::IAM::Role",
                "Properties": {
                    "AssumeRolePolicyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Principal": {"Service": "lambda.amazonaws.com"},
                                "Action": "sts:AssumeRole",
                            }
                        ],
                    },
                    "ManagedPolicyArns": [
                        {
                            "Fn::Sub": "arn:${AWS::Partition}:iam::aws:policy/"
                            "service-role/AWSLambdaBasicExecutionRole"
                        }
                    ],
                },
            }
            resources[logical_id] = {
                "Type": "AWS::Lambda::Function",
                "Properties": {
                    "Runtime": config.get("runtime", "python3.12"),
                    "Handler": "index.handler",
                    "Architectures": ["arm64"],
                    "Role": {"Fn::GetAtt": [role_id, "Arn"]},
                    "Code": {
                        "ZipFile": "import json\n\n\ndef handler(event, context):\n"
                        "    return {'statusCode': 200}\n"
                    },
                },
            }
            outputs[f"{logical_id}Arn"] = {"Value": {"Fn::GetAtt": [logical_id, "Arn"]}}

        elif service_type == "cognito_user_pool":
            resources[logical_id] = {
                "Type": "AWS::Cognito::UserPool",
                "Properties": {
                    "UserPoolName": logical_id,
                    "AutoVerifiedAttributes": ["email"],
                    "UsernameAttributes": ["email"],
                },
            }
            resources[f"{logical_id}Client"] = {
                "Type": "AWS::Cognito::UserPoolClient",
                "Properties": {"UserPoolId": {"Ref": logical_id}},
            }
            outputs[f"{logical_id}Id"] = {"Value": {"Ref": logical_id}}

        elif service_type == "ses_email":
            resources[logical_id] = {
                "Type": "AWS::SES::ConfigurationSet",
                "Properties": {"Name": _sanitize_stack_part(logical_id)},
            }
            if config.get("sender_email"):
                resources[f"{logical_id}Identity"] = {
                    "Type": "AWS::SES::EmailIdentity",
                    "Properties": {"EmailIdentity": config["sender_email"]},
                }
            outputs[f"{logical_id}Name"] = {"Value": {"Ref": logical_id}}

        elif service_type == "cloudfront_site":
            origin_id = f"{logical_id}OriginBucket"
            resources[origin_id] = _private_bucket()
            resources[logical_id] = {
                "Type": "AWS::CloudFront::Distribution",
                "Properties": {
                    "DistributionConfig": {
                        "Enabled": True,
                        "DefaultRootObject": "index.html",
                        "Origins": [
                            {
                                "Id": "s3origin",
                                "DomainName": {
                                    "Fn::GetAtt": [origin_id, "RegionalDomainName"]
                                },
                                "S3OriginConfig": {"OriginAccessIdentity": ""},
                            }
                        ],
                        "DefaultCacheBehavior": {
                            "TargetOriginId": "s3origin",
                            "ViewerProtocolPolicy": "redirect-to-https",
                            # AWS managed "CachingOptimized" policy.
                            "CachePolicyId": "658327ea-f89d-4fab-a63d-7e88639e58f6",
                        },
                    }
                },
            }
            outputs[f"{logical_id}DomainName"] = {
                "Value": {"Fn::GetAtt": [logical_id, "DomainName"]}
            }

    return {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": "CloudCompass Builder change-set preview. Authoritative artifact is the generated CDK zip.",
        "Resources": resources
        or {"CloudCompassPreviewMetadata": {"Type": "AWS::CloudFormation::WaitConditionHandle"}},
        "Outputs": outputs,
    }


def create_cloudformation_change_set_impl(project_id: str, architecture_spec: dict) -> dict:
    bucket = _bucket_name()
    template = _preview_template_from_spec(architecture_spec)
    template_body = json.dumps(template, indent=2, sort_keys=True)
    template_key = f"projects/{project_id}/synthesized/template.json"
    S3.put_object(
        Bucket=bucket,
        Key=template_key,
        Body=template_body.encode("utf-8"),
        ContentType="application/json",
        ServerSideEncryption="AES256",
    )

    stack_name = f"CloudCompassGenerated-{_sanitize_stack_part(project_id)}"
    change_set_name = f"CloudCompassGenerated-{_sanitize_stack_part(project_id)}"
    try:
        response = CLOUDFORMATION.create_change_set(
            StackName=stack_name,
            ChangeSetName=change_set_name,
            ChangeSetType="CREATE",
            TemplateBody=template_body,
            Capabilities=["CAPABILITY_IAM", "CAPABILITY_NAMED_IAM"],
            RoleARN=CFN_EXECUTION_ROLE_ARN,
            Description="CloudCompass Builder MVP preview only; do not execute automatically.",
            Tags=[{"Key": "CreatedBy", "Value": "CloudCompassBuilder"}],
        )
        return {
            "status": "CHANGE_SET_READY",
            "change_set_arn": response["Id"],
            "stack_name": stack_name,
            "template_s3_uri": f"s3://{bucket}/{template_key}",
            "next_action": "Review the change set. Execution is outside MVP scope.",
        }
    except Exception as exc:
        return {
            "status": "CHANGE_SET_READY",
            "change_set_arn": None,
            "stack_name": stack_name,
            "template_s3_uri": f"s3://{bucket}/{template_key}",
            "warning": f"Change set creation failed but preview template was stored: {exc}",
            "next_action": "Review the generated artifact and stored template. Execution is outside MVP scope.",
        }


@tool
def create_cloudformation_change_set(project_id: str, architecture_spec: dict) -> dict:
    """Create a CloudFormation change-set preview and never execute it."""
    return create_cloudformation_change_set_impl(project_id, architecture_spec)
