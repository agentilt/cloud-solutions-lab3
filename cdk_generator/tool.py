"""Agent-facing entry point for the deterministic CDK generator."""
from __future__ import annotations

from cdk_generator import generator
from cdk_generator.models import ArchitectureSpec


def generate_cdk_project(architecture_spec: dict) -> dict:
    """Generate a Python CDK project from an architecture spec."""
    generator.validate_spec(architecture_spec)
    spec = ArchitectureSpec.from_dict(architecture_spec)
    files = generator.render_project(spec)
    return {
        "project_name": spec.project_name,
        "files": files,
        "warnings": [
            "MVP generator supports S3, Lambda/API Gateway, and DynamoDB only.",
            "CloudFront, Cognito, and SES are represented in the CloudCompass app and report.",
        ],
    }
