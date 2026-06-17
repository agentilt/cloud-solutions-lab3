"""Clean, agent-facing entry point for the CDK generator.

This is the single function WS1 wraps as a Strands `@tool` (they own the
decorator + the AgentCore wiring; I own the signature + behavior). Keep this
surface small and stable — it is part of the cross-workstream contract.

WS1 will do something like:

    from strands import tool
    from cdk_generator import generate_cdk_project

    @tool
    def generate_cdk(architecture_spec: dict) -> dict:
        '''Render a Python CDK project from an architecture spec.'''
        return generate_cdk_project(architecture_spec)

This module does NOT import strands and does NOT touch AWS — that keeps the
generator deterministic and unit-testable in isolation.
"""
from __future__ import annotations

from cdk_generator import generator
from cdk_generator.models import ArchitectureSpec


def generate_cdk_project(architecture_spec: dict) -> dict:
    """Generate a Python CDK project from a validated architecture spec.

    Args:
        architecture_spec: dict matching architecture_spec.schema.json
            (produced by WS1's Architecture Designer Agent).

    Returns:
        {
          "project_name": str,
          "files": { "<relative/path>": "<source text>", ... },
          "warnings": [ ... ],
        }

    Raises:
        SpecValidationError: if the spec does not match the schema.

    TODO(diego): validate -> from_dict -> render_project -> shape the response.
    """
    _ = (generator, ArchitectureSpec, architecture_spec)
    raise NotImplementedError
