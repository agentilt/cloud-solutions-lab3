"""Maps a canonical service `type` to the Jinja2 template that renders it.

This is the single source of truth for "which service patterns can the
generator emit". The Architecture Designer (WS1) should only emit `type` values
that exist here; anything else is rejected at validation time.

Start with 3-4 canonical templates (S3, Lambda+API Gateway, DynamoDB) and grow.

TODO(diego): wire each entry to a real template file under templates/.
"""
from __future__ import annotations

# Canonical service type -> template filename (relative to templates/).
TEMPLATE_REGISTRY: dict[str, str] = {
    "s3_bucket": "services/s3_bucket.py.j2",
    "lambda_api": "services/lambda_api.py.j2",
    "dynamodb_table": "services/dynamodb_table.py.j2",
    # TODO(diego): "vpc_basics", "cloudfront_site", "cognito_user_pool", ...
}

# Project-level scaffolding templates (always rendered, regardless of services).
PROJECT_TEMPLATES: dict[str, str] = {
    "app.py": "project/app.py.j2",
    "cdk.json": "project/cdk.json.j2",
    "requirements.txt": "project/requirements.txt.j2",
    "README.md": "project/README.md.j2",
}


def template_for(service_type: str) -> str:
    """Return the template path for a service type, or raise if unknown."""
    try:
        return TEMPLATE_REGISTRY[service_type]
    except KeyError as exc:  # noqa: F841
        raise KeyError(
            f"unknown service type {service_type!r}; "
            f"supported: {sorted(TEMPLATE_REGISTRY)}"
        ) from exc


def supported_types() -> list[str]:
    """Service types the generator can currently emit (used by WS1 + tests)."""
    return sorted(TEMPLATE_REGISTRY)
