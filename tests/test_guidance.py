"""Unit tests for the RAG guidance tool (Bedrock Knowledge Base + curated fallback)."""
import importlib
import sys


def _tools(monkeypatch, kb_id=None):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    if kb_id:
        monkeypatch.setenv("KNOWLEDGE_BASE_ID", kb_id)
    else:
        monkeypatch.delenv("KNOWLEDGE_BASE_ID", raising=False)
    sys.modules.pop("agent.tools", None)
    return importlib.import_module("agent.tools")


def _patch_retrieve(monkeypatch, tools, fake_client):
    original = tools.boto3.client
    monkeypatch.setattr(
        tools.boto3,
        "client",
        lambda name, *a, **k: fake_client if name == "bedrock-agent-runtime" else original(name, *a, **k),
    )


def test_guidance_falls_back_without_kb(monkeypatch):
    tools = _tools(monkeypatch)  # KNOWLEDGE_BASE_ID unset
    out = tools.query_reference_guidance_impl("bakery", "serverless-web-application")
    assert out["source"] == "curated-fallback"
    assert out["guidance"]


def test_guidance_uses_kb_when_configured(monkeypatch):
    tools = _tools(monkeypatch, kb_id="KB123")

    class FakeRT:
        def retrieve(self, **kwargs):
            assert kwargs["knowledgeBaseId"] == "KB123"
            assert kwargs["retrievalQuery"]["text"]
            return {
                "retrievalResults": [
                    {"content": {"text": "Use CloudFront OAC."}, "location": {"type": "S3"}, "score": 0.9}
                ]
            }

    _patch_retrieve(monkeypatch, tools, FakeRT())
    out = tools.query_reference_guidance_impl("static website", "serverless-web-application")
    assert out["source"] == "bedrock-knowledge-base"
    assert out["matches"][0]["text"] == "Use CloudFront OAC."


def test_guidance_falls_back_on_kb_error(monkeypatch):
    tools = _tools(monkeypatch, kb_id="KB123")

    class FakeRT:
        def retrieve(self, **kwargs):
            raise RuntimeError("kb unavailable")

    _patch_retrieve(monkeypatch, tools, FakeRT())
    out = tools.query_reference_guidance_impl("x", "y")
    assert out["source"] == "curated-fallback"
