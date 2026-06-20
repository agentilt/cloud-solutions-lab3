import json
from pathlib import Path

from cdk_generator import generate_cdk_project

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "cdk_generator" / "schema" / "examples"


def _load_example(name: str) -> dict:
    return json.loads((EXAMPLES_DIR / name).read_text(encoding="utf-8"))


def test_s3_only_contains_expected_files_and_constructs():
    result = generate_cdk_project(_load_example("s3_only.json"))

    assert result["project_name"] == "static-assets"
    assert sorted(result["files"]) == [
        "README.md",
        "app.py",
        "cdk.json",
        "cloudcompass_generated/__init__.py",
        "cloudcompass_generated/generated_stack.py",
        "requirements.txt",
    ]
    stack = result["files"]["cloudcompass_generated/generated_stack.py"]
    assert "s3.Bucket(" in stack
    assert "BlockPublicAccess.BLOCK_ALL" in stack
    assert "enforce_ssl=True" in stack


def test_rendering_is_deterministic():
    spec = _load_example("bakery.json")
    first = generate_cdk_project(spec)
    second = generate_cdk_project(spec)

    assert first == second


def test_full_web_app_renders_all_service_constructs():
    """The expanded catalog (CloudFront, Cognito, SES) renders + compiles."""
    result = generate_cdk_project(_load_example("full_web_app.json"))
    stack = result["files"]["cloudcompass_generated/generated_stack.py"]
    for needle in (
        "cloudfront.Distribution(",
        "origins.S3BucketOrigin.with_origin_access_control(",
        "cognito.UserPool(",
        "ses.ConfigurationSet(",
        "ses.EmailIdentity(",
        "lambda_.Function(",
        "dynamodb.TableV2(",
        "s3.Bucket(",
    ):
        assert needle in stack, f"missing {needle!r} in generated stack"
    # conditional imports must only pull what the spec uses
    for path, source in result["files"].items():
        if path.endswith(".py"):
            compile(source, path, "exec")
