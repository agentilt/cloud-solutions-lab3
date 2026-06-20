"""Unit tests for the CloudFormation change-set preview builder in agent/tools.py.

The live CreateChangeSet call needs AWS, but the template-building logic is pure
and testable. Guards the regression where lambda_api was silently dropped.
"""
import importlib
import sys


def _tools(monkeypatch):
    # boto3 clients are created at import time; give them a region but no creds.
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    sys.modules.pop("agent.tools", None)
    return importlib.import_module("agent.tools")


_SPEC = {
    "project_name": "demo",
    "pattern": "serverless-web-application",
    "services": [
        {"type": "s3_bucket", "logical_id": "Assets", "config": {"versioned": True}},
        {"type": "dynamodb_table", "logical_id": "Orders", "config": {"sort_key": "sk"}},
        {"type": "lambda_api", "logical_id": "OrderApi", "config": {"routes": ["GET /o"]}},
        {"type": "cognito_user_pool", "logical_id": "Customers"},
        {"type": "ses_email", "logical_id": "Receipts", "config": {"sender_email": "a@b.com"}},
        {"type": "cloudfront_site", "logical_id": "Site"},
    ],
}


def test_preview_includes_a_resource_for_every_service(monkeypatch):
    tools = _tools(monkeypatch)
    template = tools._preview_template_from_spec(_SPEC)
    resource_ids = set(template["Resources"])
    # No service silently dropped: each logical_id owns at least one resource.
    for service in _SPEC["services"]:
        lid = service["logical_id"]
        assert any(rid == lid or rid.startswith(lid) for rid in resource_ids), (
            f"{lid} ({service['type']}) missing from change-set preview"
        )


def test_preview_models_previously_dropped_services(monkeypatch):
    tools = _tools(monkeypatch)
    types = {r["Type"] for r in tools._preview_template_from_spec(_SPEC)["Resources"].values()}
    # lambda_api (the regression), plus the expanded catalog.
    assert "AWS::Lambda::Function" in types
    assert "AWS::Cognito::UserPool" in types
    assert "AWS::SES::ConfigurationSet" in types
    assert "AWS::CloudFront::Distribution" in types


def test_preview_is_wellformed_cfn(monkeypatch):
    tools = _tools(monkeypatch)
    template = tools._preview_template_from_spec(_SPEC)
    assert template["AWSTemplateFormatVersion"] == "2010-09-09"
    assert template["Resources"]
    # every resource has a Type and a Properties dict
    for rid, resource in template["Resources"].items():
        assert resource.get("Type"), rid
        assert isinstance(resource.get("Properties", {}), dict), rid
