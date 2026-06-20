"""Guards that DynamoDB writes are float-free.

boto3's DynamoDB resource raises on Python floats. The computed cost estimate and
budget carry floats, so save_project_state_impl must convert them to Decimal.
"""
import importlib
import sys
from decimal import Decimal


def _tools(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    sys.modules.pop("agent.tools", None)
    return importlib.import_module("agent.tools")


def _has_float(obj) -> bool:
    if isinstance(obj, float):
        return True
    if isinstance(obj, dict):
        return any(_has_float(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return any(_has_float(v) for v in obj)
    return False


def test_dynamo_safe_converts_floats_recursively(monkeypatch):
    tools = _tools(monkeypatch)
    out = tools._dynamo_safe({"a": 1.5, "b": [2.0, {"c": 3.25}], "d": "x", "e": 4})
    assert out["a"] == Decimal("1.5")
    assert out["b"][1]["c"] == Decimal("3.25")
    assert out["d"] == "x" and out["e"] == 4
    assert not _has_float(out)


def test_cost_estimate_round_trips_without_floats(monkeypatch):
    tools = _tools(monkeypatch)
    estimate = tools.get_service_pricing_impl("us-east-1", {"output_tokens": 5000})
    assert _has_float(estimate)  # the raw estimate has floats...
    assert not _has_float(tools._dynamo_safe(estimate))  # ...but is safe after conversion


def test_save_project_state_writes_no_floats(monkeypatch):
    """Integration point: cost estimate + float budget must reach update_item as Decimal."""
    tools = _tools(monkeypatch)
    captured: dict = {}

    class FakeTable:
        def update_item(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(tools, "_table", lambda: FakeTable())
    tools.save_project_state_impl(
        "u",
        "p",
        "VALIDATING",
        {
            "cost_estimate_json": tools.get_service_pricing_impl("us-east-1", {}),
            "architecture_spec_json": {"budget_monthly_usd": 200.0},
        },
    )
    assert not _has_float(captured["ExpressionAttributeValues"])


def test_save_project_state_escapes_reserved_keywords(monkeypatch):
    """`status` and `ttl` are DynamoDB reserved keywords; both must be escaped or
    UpdateItem fails with a ValidationException (caught only on a real table)."""
    tools = _tools(monkeypatch)
    captured: dict = {}

    class FakeTable:
        def update_item(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(tools, "_table", lambda: FakeTable())
    tools.save_project_state_impl("u", "p", "DESIGNING", {"prompt": "x"})
    expr = captured["UpdateExpression"]
    names = captured["ExpressionAttributeNames"]
    assert "#status = :status" in expr and names["#status"] == "status"
    assert "#ttl = :ttl" in expr and names["#ttl"] == "ttl"
