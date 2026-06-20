import importlib
import json
import os
import sys
from types import SimpleNamespace


class FakeTable:
    def __init__(self):
        self.items = {}
        self.put_calls = []
        self.update_calls = []

    def put_item(self, Item):
        self.put_calls.append(Item)
        self.items[(Item["pk"], Item["sk"])] = Item

    def get_item(self, Key):
        item = self.items.get((Key["pk"], Key["sk"]))
        return {"Item": item} if item else {}

    def update_item(self, **kwargs):
        self.update_calls.append(kwargs)


class FakeAgentCore:
    def invoke_agent_runtime(self, **_kwargs):
        payload = {
            "status": "CHANGE_SET_READY",
            "architecture_summary": "summary",
        }
        return {"response": SimpleNamespace(read=lambda: json.dumps(payload).encode("utf-8"))}


class FakeS3:
    def generate_presigned_url(self, **_kwargs):
        return "https://signed.example/artifact.zip"


def _load_module(monkeypatch):
    monkeypatch.setenv("AGENT_RUNTIME_ARN", "arn:aws:agentcore:runtime/test")
    monkeypatch.setenv("DATA_BUCKET_NAME", "bucket")
    monkeypatch.setenv("DATA_TABLE_NAME", "table")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    sys.modules.pop("lambdas.projects.handler", None)
    module = importlib.import_module("lambdas.projects.handler")
    module.TABLE = FakeTable()
    module.AGENTCORE = FakeAgentCore()
    module.S3 = FakeS3()
    return module


def _event(method="POST", body=None, project_id=None, user_id="user-123"):
    path = "/projects" if not project_id else f"/projects/{project_id}"
    return {
        "rawPath": path,
        "pathParameters": {"project_id": project_id} if project_id else {},
        "body": json.dumps(body or {}),
        "requestContext": {
            "http": {"method": method},
            "authorizer": {"jwt": {"claims": {"sub": user_id}}},
        },
    }


def test_create_requires_authenticated_user(monkeypatch):
    module = _load_module(monkeypatch)
    event = _event(body={"prompt": "x"})
    event["requestContext"]["authorizer"]["jwt"]["claims"] = {}

    response = module.handler(event, None)

    assert response["statusCode"] == 401


def test_create_rejects_missing_prompt(monkeypatch):
    module = _load_module(monkeypatch)

    response = module.handler(_event(body={}), None)

    assert response["statusCode"] == 400
    assert "prompt" in json.loads(response["body"])["error"]


def test_create_uses_jwt_user_for_project_key(monkeypatch):
    module = _load_module(monkeypatch)

    response = module.handler(_event(body={"prompt": "build bakery", "user_id": "attacker"}), None)

    assert response["statusCode"] == 202
    stored = module.TABLE.put_calls[0]
    assert stored["pk"] == "USER#user-123"
    assert stored["user_id"] == "user-123"


def test_get_project_returns_user_scoped_item(monkeypatch):
    module = _load_module(monkeypatch)
    module.TABLE.items[("USER#user-123", "PROJECT#p1")] = {
        "pk": "USER#user-123",
        "sk": "PROJECT#p1",
        "project_id": "p1",
        "status": "CHANGE_SET_READY",
        "artifact_s3_key": "projects/p1/source/cdk-project.zip",
    }

    response = module.handler(_event(method="GET", project_id="p1"), None)
    body = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert body["project_id"] == "p1"
    assert body["cdk_artifact_download_url"].startswith("https://signed.example")
