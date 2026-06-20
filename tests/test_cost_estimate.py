"""Unit tests for the per-run cost estimator in agent/tools.py.

The Price List API call is best-effort (offline in CI), but the cost must be
COMPUTED from the usage profile and the returned rates, not hardcoded.
"""
import importlib
import sys


def _tools(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    sys.modules.pop("agent.tools", None)
    return importlib.import_module("agent.tools")


def test_cost_is_computed_from_usage_and_returned_rates(monkeypatch):
    tools = _tools(monkeypatch)
    est = tools.get_service_pricing_impl(
        "us-east-1",
        {"prompt_tokens": 4000, "output_tokens": 6000, "codebuild_minutes": 3},
    )
    r, a = est["rates_usd"], est["assumptions"]
    expected = (
        a["prompt_tokens"] / 1000 * r["bedrock_input_per_1k_usd"]
        + a["output_tokens"] / 1000 * r["bedrock_output_per_1k_usd"]
        + a["codebuild_minutes"] * r["codebuild_small_per_min_usd"]
        + r["platform_overhead_per_run_usd"]
    )
    # robust whether the Price List API was reachable or not (uses returned rates)
    assert abs(est["estimated_cost_usd"] - round(expected, 4)) < 0.001
    assert isinstance(est["estimated_cost_usd"], (int, float))
    assert est["unit"] == "infrastructure-generation-run"
    assert {li["component"] for li in est["line_items"]} >= {
        "Bedrock model inference",
        "CodeBuild validation",
    }


def test_cost_scales_with_output_tokens(monkeypatch):
    tools = _tools(monkeypatch)
    cheap = tools.get_service_pricing_impl("us-east-1", {"output_tokens": 1000})
    pricey = tools.get_service_pricing_impl("us-east-1", {"output_tokens": 100_000})
    assert pricey["estimated_cost_usd"] > cheap["estimated_cost_usd"]


def test_pricing_source_is_declared(monkeypatch):
    tools = _tools(monkeypatch)
    est = tools.get_service_pricing_impl("us-east-1", {})
    assert est["pricing_source"] in {"aws-price-list-api", "curated-rate-offline"}
