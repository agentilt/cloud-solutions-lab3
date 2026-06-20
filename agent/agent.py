"""CloudCompass Builder — model-driven multi-agent orchestration on Bedrock AgentCore.

A Sonnet-class orchestrator decomposes the user's natural-language AWS
infrastructure request and drives the workflow by calling specialist sub-agents
and deterministic AWS @tools. There is NO deterministic fallback pipeline — the
model reasons and acts end to end. The deterministic work (rendering CDK, writing
artifacts to S3, validation, change sets) lives inside @tool functions, so the
*actions* are repeatable and the tools persist their own results to DynamoDB for
the UI; the *reasoning and orchestration* are the model's.

Specialist topology:
  - orchestrator          (Sonnet)  drives the end-to-end workflow
  - requirements analyst  (Haiku)   extracts workload/budget from the prompt
  - architecture designer (Sonnet)  emits a validated architecture spec
Mechanical steps (generate/validate/build/cost/change-set) are direct tools.
"""
from __future__ import annotations

import os
import re
from typing import Any

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from pydantic import BaseModel, Field
from strands import Agent, tool
from strands.models import BedrockModel

from cdk_generator import generator
from tools import (
    create_cloudformation_change_set_impl,
    get_project_state_impl,
    get_service_pricing_impl,
    query_reference_guidance_impl,
    render_cdk_project_impl,
    save_project_state_impl,
    start_validation_build_impl,
    validate_generated_template_impl,
    write_cdk_project_impl,
)

SUPPORTED_SERVICE_TYPES = generator.registry.supported_types()
DEFAULT_REGION = os.environ.get("AWS_REGION", "us-east-1")


# --------------------------------------------------------------------------- #
# Model factory                                                               #
# --------------------------------------------------------------------------- #
def _model(region: str | None = None, *, fast: bool = False) -> BedrockModel:
    """Build a Bedrock model for the runtime's execution role.

    Defaults to Strands' Sonnet-class inference profile (handoff: Sonnet for
    orchestration, Haiku for cheap subtasks). BEDROCK_MODEL_ID /
    BEDROCK_FAST_MODEL_ID override. A Bedrock Guardrail is attached when
    BEDROCK_GUARDRAIL_ID is set (infra wiring tracked in task #10).
    """
    kwargs: dict[str, Any] = {"region_name": region or DEFAULT_REGION}
    model_id = os.environ.get("BEDROCK_FAST_MODEL_ID" if fast else "BEDROCK_MODEL_ID")
    if model_id:
        kwargs["model_id"] = model_id
    guardrail_id = os.environ.get("BEDROCK_GUARDRAIL_ID")
    if guardrail_id:
        kwargs["guardrail_id"] = guardrail_id
        kwargs["guardrail_version"] = os.environ.get("BEDROCK_GUARDRAIL_VERSION", "DRAFT")
    return BedrockModel(**kwargs)


# --------------------------------------------------------------------------- #
# Architecture-designer structured output                                     #
# --------------------------------------------------------------------------- #
class _ServiceSpec(BaseModel):
    type: str = Field(description="One of: " + ", ".join(SUPPORTED_SERVICE_TYPES))
    logical_id: str = Field(description="Alphanumeric CDK construct id, unique per project")
    config: dict[str, Any] = Field(default_factory=dict)


class _ArchitectureSpec(BaseModel):
    project_name: str = Field(description="lowercase-hyphenated, e.g. 'online-bakery'")
    pattern: str = "serverless-web-application"
    deployment_boundary: str = "change-set-only"
    budget_monthly_usd: float | None = None
    services: list[_ServiceSpec]


def _coerce_to_schema(spec: dict) -> dict:
    """Coerce a model-proposed spec to the generator's schema constraints.

    project_name -> ^[a-z][a-z0-9-]{1,48}$ ; logical_id -> ^[A-Za-z][A-Za-z0-9]{1,63}$
    so a slightly-off model output still validates instead of hard-failing.
    """
    name = re.sub(r"[^a-z0-9-]", "-", str(spec.get("project_name", "project")).lower())
    name = re.sub(r"-+", "-", name).strip("-") or "project"
    if not name[0].isalpha():
        name = f"app-{name}"
    spec["project_name"] = name[:49]

    for service in spec.get("services", []):
        lid = re.sub(r"[^A-Za-z0-9]", "", str(service.get("logical_id", "")))
        if not lid or not lid[0].isalpha():
            lid = "Svc" + lid
        service["logical_id"] = lid[:64]
        service.setdefault("config", {})
    spec.setdefault("pattern", "serverless-web-application")
    spec.setdefault("deployment_boundary", "change-set-only")
    return spec


# --------------------------------------------------------------------------- #
# Specialist system prompts                                                    #
# --------------------------------------------------------------------------- #
ORCHESTRATOR_PROMPT = f"""
You are CloudCompass Builder's orchestration agent. You turn a user's
natural-language AWS infrastructure request into a governed, validated,
cost-estimated, deployable Python CDK project plus a CloudFormation CHANGE SET.
You never execute a deployment — the MVP stops at a change set for human review.

Run this workflow by calling your tools, in order. Do not invent results.
1. Call analyze_requirements with the user's prompt to extract the workload.
2. Call query_reference_guidance to retrieve approved architecture guidance.
3. Call design_architecture with the requirements to get a validated spec. Only
   these service types are supported: {", ".join(SUPPORTED_SERVICE_TYPES)}.
4. Call generate_and_store_cdk with that spec to render the CDK project, run a
   security check, and store the artifact in S3.
5. Call run_validation_build with the returned artifact_s3_uri.
6. Call estimate_run_cost to estimate the cost of THIS generation run.
7. Call create_change_set with the spec to produce the change-set preview.
8. Finish with a short summary of what you built, the validation outcome, the
   cost, and the change-set status. Remind the user execution is out of scope.

Each tool persists its own state, so always pass the real values returned by the
previous tool. If a tool returns an error, explain it; do not fabricate success.
""".strip()

REQUIREMENTS_PROMPT = """
You are the requirements analyst. From a natural-language AWS infrastructure
request, extract: business_type, workload_type, whether the app needs a
frontend / authentication / API / database / email, the monthly budget (USD) if
stated, and any missing_requirements. Respond with a concise JSON object.
""".strip()

ARCHITECTURE_PROMPT = f"""
You are the architecture designer. Given requirements, choose a minimal set of
approved services for a serverless web application. Supported service types ONLY:
{", ".join(SUPPORTED_SERVICE_TYPES)}.
Guidance: cloudfront_site for a static website, cognito_user_pool for customer
login, lambda_api for the API (set config.routes), dynamodb_table for storage
(config.partition_key/sort_key), ses_email for receipts (config.sender_email),
s3_bucket for assets. Give each service a unique alphanumeric logical_id and a
lowercase-hyphenated project_name. The deployment_boundary is always
'change-set-only'.
""".strip()


def _architecture_summary(spec: dict, guidance_source: str) -> str:
    services = ", ".join(s["type"] for s in spec.get("services", []))
    return (
        f"CloudCompass selected the {spec.get('pattern', 'serverless')} pattern "
        f"({services}). Guidance source: {guidance_source}. MVP creates a change set only."
    )


# --------------------------------------------------------------------------- #
# Per-request tool factory (binds user_id / project_id / region)              #
# --------------------------------------------------------------------------- #
def build_tools(user_id: str, project_id: str, region: str) -> list:
    """Build the orchestrator's tools, bound to this request's identity so the
    model never has to manage user_id/project_id itself."""

    @tool
    def analyze_requirements(prompt: str) -> dict:
        """Extract structured requirements from a natural-language infra request."""
        analyst = Agent(model=_model(region, fast=True), system_prompt=REQUIREMENTS_PROMPT)
        return {"requirements": str(analyst(prompt))}

    @tool
    def query_reference_guidance(query: str, workload_type: str) -> dict:
        """Retrieve approved AWS architecture guidance for the workload."""
        return query_reference_guidance_impl(query, workload_type)

    @tool
    def design_architecture(requirements: str) -> dict:
        """Produce a validated architecture spec (the CDK generator contract)."""
        designer = Agent(model=_model(region), system_prompt=ARCHITECTURE_PROMPT)
        last_error = ""
        for _attempt in range(3):
            instruction = requirements if not last_error else (
                f"{requirements}\n\nYour previous spec was invalid: {last_error}. Fix it."
            )
            result = designer(instruction, structured_output_model=_ArchitectureSpec)
            spec_model = result.structured_output
            if spec_model is None:
                last_error = "no structured spec returned"
                continue
            spec = _coerce_to_schema(spec_model.model_dump())
            try:
                generator.validate_spec(spec)
            except Exception as exc:  # generator.SpecValidationError
                last_error = str(exc)
                continue
            return {"architecture_spec": spec}
        return {"error": f"could not produce a valid architecture spec: {last_error}"}

    @tool
    def generate_and_store_cdk(architecture_spec: dict) -> dict:
        """Render the CDK project, run a security check, and store it in S3."""
        generated = render_cdk_project_impl(architecture_spec)
        validation = validate_generated_template_impl(generated["files"])
        artifact = write_cdk_project_impl(user_id, project_id, generated["files"])
        summary = _architecture_summary(architecture_spec, "agent-designed")
        save_project_state_impl(
            user_id,
            project_id,
            "VALIDATING",
            {
                "architecture_spec_json": architecture_spec,
                "architecture_summary": summary,
                "cdk_artifact_s3_uri": artifact["artifact_s3_uri"],
                "artifact_s3_key": artifact["artifact_s3_key"],
                "generator_warnings": generated["warnings"],
                "validation_summary": validation,
                "security_findings_json": validation,
            },
        )
        return {
            "artifact_s3_uri": artifact["artifact_s3_uri"],
            "validation_summary": validation,
            "warnings": generated["warnings"],
        }

    @tool
    def run_validation_build(artifact_s3_uri: str) -> dict:
        """Start the CodeBuild validation build for a stored CDK artifact."""
        build = start_validation_build_impl(project_id, artifact_s3_uri)
        save_project_state_impl(user_id, project_id, "VALIDATING", {"validation_build": build})
        return build

    @tool
    def estimate_run_cost(prompt_tokens: int, output_tokens: int, codebuild_minutes: float) -> dict:
        """Estimate the cost of this one infrastructure-generation run."""
        estimate = get_service_pricing_impl(
            region,
            {
                "prompt_tokens": prompt_tokens,
                "output_tokens": output_tokens,
                "codebuild_minutes": codebuild_minutes,
            },
        )
        save_project_state_impl(user_id, project_id, "VALIDATING", {"cost_estimate_json": estimate})
        return estimate

    @tool
    def create_change_set(architecture_spec: dict) -> dict:
        """Create the CloudFormation change-set preview and stop (never execute)."""
        change_set = create_cloudformation_change_set_impl(project_id, architecture_spec)
        save_project_state_impl(
            user_id,
            project_id,
            "CHANGE_SET_READY",
            {
                "change_set_arn": change_set.get("change_set_arn"),
                "change_set_stack_name": change_set.get("stack_name"),
                "synthesized_template_s3_uri": change_set.get("template_s3_uri"),
                "next_action": change_set.get(
                    "next_action", "Review the change set. Execution is outside MVP scope."
                ),
            },
        )
        return change_set

    return [
        analyze_requirements,
        query_reference_guidance,
        design_architecture,
        generate_and_store_cdk,
        run_validation_build,
        estimate_run_cost,
        create_change_set,
    ]


app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload: dict) -> dict:
    user_id = payload["user_id"]
    project_id = payload["project_id"]
    prompt = payload.get("prompt", "")
    region = payload.get("region", DEFAULT_REGION)

    save_project_state_impl(user_id, project_id, "DESIGNING", {"prompt": prompt, "region": region})

    orchestrator = Agent(
        model=_model(region),
        system_prompt=ORCHESTRATOR_PROMPT,
        tools=build_tools(user_id, project_id, region),
        name="cloudcompass-orchestrator",
    )
    result = orchestrator(prompt)

    state = get_project_state_impl(user_id, project_id)
    return {
        "project_id": project_id,
        "status": state.get("status", "DESIGNING"),
        "architecture_summary": state.get("architecture_summary"),
        "cdk_artifact_s3_uri": state.get("cdk_artifact_s3_uri"),
        "validation_summary": state.get("validation_summary"),
        "cost_estimate": state.get("cost_estimate_json"),
        "change_set_arn": state.get("change_set_arn"),
        "next_action": state.get(
            "next_action", "Review the change set. Execution is outside MVP scope."
        ),
        "agent_message": str(result),
    }


if __name__ == "__main__":
    app.run()
