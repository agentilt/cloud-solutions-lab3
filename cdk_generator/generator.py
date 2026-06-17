"""Core deterministic CDK renderer.

Pipeline:
    raw spec dict
      -> validate_spec()        (jsonschema against architecture_spec.schema.json)
      -> ArchitectureSpec       (models.from_dict)
      -> render_project()       (Jinja2, per-service + project scaffolding)
      -> {relative_path: source_text}

Determinism rules (do not break — the snapshot tests depend on them):
  - no timestamps, UUIDs, or env lookups baked into output
  - stable ordering of services and rendered files
  - no LLM calls anywhere in this module

TODO(diego): implement once the schema + first template (s3_bucket) are locked.
"""
from __future__ import annotations

import json
from pathlib import Path

# import jinja2  # TODO(diego): add to requirements once rendering is implemented
# import jsonschema

from cdk_generator.models import ArchitectureSpec
from cdk_generator import registry

_SCHEMA_PATH = Path(__file__).parent / "schema" / "architecture_spec.schema.json"
_TEMPLATES_DIR = Path(__file__).parent / "templates"


def load_schema() -> dict:
    """Load the architecture-spec JSON Schema (the WS1<->WS2 contract)."""
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_spec(raw: dict) -> None:
    """Validate a raw spec dict against the schema. Raise on invalid input.

    TODO(diego): jsonschema.validate(raw, load_schema()); translate errors into
    a clean exception WS1 can surface to the user.
    """
    raise NotImplementedError


def _build_env():
    """Create the Jinja2 Environment (autoescape off — we render Python, not HTML).

    TODO(diego): FileSystemLoader(_TEMPLATES_DIR), trim_blocks/lstrip_blocks=True
    for clean output, keep_trailing_newline=True for stable snapshots.
    """
    raise NotImplementedError


def render_project(spec: ArchitectureSpec) -> dict[str, str]:
    """Render a full Python CDK project as {relative_path: source_text}.

    Renders project scaffolding (registry.PROJECT_TEMPLATES) plus one construct
    block per service (registry.template_for), assembled into stack file(s).

    TODO(diego): implement deterministic assembly + return mapping.
    """
    _ = (spec, registry, _build_env)  # silence linters until implemented
    raise NotImplementedError
