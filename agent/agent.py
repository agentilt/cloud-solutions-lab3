"""CloudCompass Builder Strands app deployed to Bedrock AgentCore Runtime."""
from __future__ import annotations

import json

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent

from tools import (
    build_bakery_architecture_spec,
    create_cloudformation_change_set,
    create_cloudformation_change_set_impl,
    get_service_pricing,
    get_service_pricing_impl,
    query_reference_guidance,
    query_reference_guidance_impl,
    render_cdk_project,
    render_cdk_project_impl,
    save_project_state,
    save_project_state_impl,
    start_validation_build,
    start_validation_build_impl,
    validate_generated_template,
    validate_generated_template_impl,
    write_cdk_project,
    write_cdk_project_impl,
)

ORCHESTRATOR_PROMPT = """
You are CloudCompass Builder's orchestration agent. Convert a user's AWS
infrastructure request into a safe, validated, deployable Python CDK project.
Use approved patterns, persist project state, and never execute deployment.
The MVP stops after creating a CloudFormation change set.
"""

REQUIREMENTS_PROMPT = """
You are the requirements analyst. Extract the workload type, budget, and missing
information from a natural-language infrastructure request.
"""

ARCHITECTURE_PROMPT = """
You are the architecture designer. Prefer the approved serverless bakery/shop
pattern: S3, CloudFront, Cognito, HTTP API, Lambda, DynamoDB, SES, CloudWatch,
and least-privilege IAM. Use retrieved guidance when available.
"""

CDK_PROMPT = """
You are the CDK generator agent. Use the deterministic render_cdk_project tool
instead of inventing CDK source manually.
"""

SECURITY_PROMPT = """
You are the security reviewer. Check for wildcard IAM, public S3 exposure,
encryption, logging, and the no-auto-deploy MVP boundary.
"""

COST_PROMPT = """
You are the cost estimator. Estimate cost per infrastructure-generation run.
"""

DEPLOYMENT_PROMPT = """
You are the deployment orchestrator. Store artifacts, start validation, create a
CloudFormation change set, and never execute it.
"""

orchestrator_agent = Agent(
    system_prompt=ORCHESTRATOR_PROMPT,
    tools=[
        query_reference_guidance,
        render_cdk_project,
        write_cdk_project,
        save_project_state,
        start_validation_build,
        validate_generated_template,
        get_service_pricing,
        create_cloudformation_change_set,
    ],
)

# Specialist agents document the intended topology and can be used directly as
# the project grows. The MVP workflow below stays deterministic for the demo.
requirements_agent = Agent(system_prompt=REQUIREMENTS_PROMPT, tools=[save_project_state])
architecture_agent = Agent(system_prompt=ARCHITECTURE_PROMPT, tools=[query_reference_guidance])
cdk_generator_agent = Agent(system_prompt=CDK_PROMPT, tools=[render_cdk_project])
security_reviewer_agent = Agent(system_prompt=SECURITY_PROMPT, tools=[validate_generated_template])
cost_estimator_agent = Agent(system_prompt=COST_PROMPT, tools=[get_service_pricing])
deployment_orchestrator_agent = Agent(
    system_prompt=DEPLOYMENT_PROMPT,
    tools=[write_cdk_project, start_validation_build, create_cloudformation_change_set],
)

app = BedrockAgentCoreApp()


def _architecture_summary(spec: dict, guidance: dict) -> str:
    services = ", ".join(service["type"] for service in spec["services"])
    source = guidance.get("source", "curated-fallback")
    return (
        f"CloudCompass selected the serverless bakery/shop pattern using {services}. "
        f"Guidance source: {source}. The MVP creates a change set only."
    )


@app.entrypoint
def invoke(payload: dict) -> dict:
    user_id = payload["user_id"]
    project_id = payload["project_id"]
    prompt = payload.get("prompt", "")
    region = payload.get("region", "us-east-1")

    save_project_state_impl(user_id, project_id, "DESIGNING", {"prompt": prompt, "region": region})

    guidance = query_reference_guidance_impl(prompt, "serverless-web-application")
    architecture_spec = build_bakery_architecture_spec(prompt)
    requirements_json = {
        "business_type": "online bakery",
        "workload_type": "serverless web application",
        "frontend_required": True,
        "authentication_required": True,
        "api_required": True,
        "database_required": True,
        "email_required": True,
        "monthly_budget_usd": architecture_spec.get("budget_monthly_usd"),
        "missing_requirements": [],
    }
    save_project_state_impl(
        user_id,
        project_id,
        "GENERATING_CDK",
        {
            "requirements_json": requirements_json,
            "architecture_spec_json": architecture_spec,
            "architecture_summary": _architecture_summary(architecture_spec, guidance),
        },
    )

    generated = render_cdk_project_impl(architecture_spec)
    artifact = write_cdk_project_impl(user_id, project_id, generated["files"])

    save_project_state_impl(
        user_id,
        project_id,
        "VALIDATING",
        {
            "cdk_artifact_s3_uri": artifact["artifact_s3_uri"],
            "artifact_s3_key": artifact["artifact_s3_key"],
            "generator_warnings": generated["warnings"],
        },
    )

    validation_summary = validate_generated_template_impl(generated["files"])
    validation_build = start_validation_build_impl(project_id, artifact["artifact_s3_uri"])
    cost_estimate = get_service_pricing_impl(
        region,
        {"prompt_tokens": 4000, "output_tokens": 6000, "codebuild_minutes": 3},
    )
    change_set = create_cloudformation_change_set_impl(project_id, architecture_spec)

    final_metadata = {
        "architecture_summary": _architecture_summary(architecture_spec, guidance),
        "cdk_artifact_s3_uri": artifact["artifact_s3_uri"],
        "artifact_s3_key": artifact["artifact_s3_key"],
        "validation_summary": validation_summary,
        "validation_build": validation_build,
        "cost_estimate_json": cost_estimate,
        "security_findings_json": validation_summary,
        "synthesized_template_s3_uri": change_set.get("template_s3_uri"),
        "change_set_arn": change_set.get("change_set_arn"),
        "change_set_stack_name": change_set.get("stack_name"),
        "next_action": change_set.get(
            "next_action", "Review the change set. Execution is outside MVP scope."
        ),
    }
    save_project_state_impl(user_id, project_id, "CHANGE_SET_READY", final_metadata)

    return {
        "project_id": project_id,
        "status": "CHANGE_SET_READY",
        "architecture_summary": final_metadata["architecture_summary"],
        "cdk_artifact_s3_uri": artifact["artifact_s3_uri"],
        "validation_summary": validation_summary,
        "cost_estimate": cost_estimate,
        "change_set_arn": change_set.get("change_set_arn"),
        "next_action": final_metadata["next_action"],
    }


if __name__ == "__main__":
    app.run()
