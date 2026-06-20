"""Core deterministic CDK renderer."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import jinja2
import jsonschema

from cdk_generator import registry
from cdk_generator.models import ArchitectureSpec

_SCHEMA_PATH = Path(__file__).parent / "schema" / "architecture_spec.schema.json"
_TEMPLATES_DIR = Path(__file__).parent / "templates"


class SpecValidationError(ValueError):
    """Raised when an architecture spec violates the generator contract."""


def load_schema() -> dict:
    """Load the architecture-spec JSON Schema."""
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_spec(raw: dict) -> None:
    """Validate a raw spec dict against the schema and local invariants."""
    validator = jsonschema.Draft202012Validator(load_schema())
    errors = sorted(validator.iter_errors(raw), key=lambda error: list(error.path))
    if errors:
        first = errors[0]
        path = ".".join(str(part) for part in first.path) or "$"
        raise SpecValidationError(f"{path}: {first.message}")

    logical_ids = [service["logical_id"] for service in raw["services"]]
    duplicates = sorted({value for value in logical_ids if logical_ids.count(value) > 1})
    if duplicates:
        raise SpecValidationError(f"services.logical_id must be unique: {duplicates}")

    unsupported = sorted(
        {service["type"] for service in raw["services"]} - set(registry.supported_types())
    )
    if unsupported:
        raise SpecValidationError(
            f"unsupported service type(s): {unsupported}; supported: {registry.supported_types()}"
        )


def _snake_case(value: str) -> str:
    value = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", value)
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    value = re.sub(r"[^A-Za-z0-9]+", "_", value)
    return value.strip("_").lower()


def _pascal_case(value: str) -> str:
    words = re.split(r"[^A-Za-z0-9]+", value)
    return "".join(word[:1].upper() + word[1:] for word in words if word)


def _bool_literal(value: Any) -> str:
    return "True" if bool(value) else "False"


def _quote(value: Any) -> str:
    return repr(value)


def _route_method(route: str) -> str:
    return route.split(maxsplit=1)[0].upper()


def _route_path(route: str) -> str:
    parts = route.split(maxsplit=1)
    return parts[1] if len(parts) == 2 else "/"


def _runtime_enum(runtime: str | None) -> str:
    mapping = {
        "python3.9": "PYTHON_3_9",
        "python3.10": "PYTHON_3_10",
        "python3.11": "PYTHON_3_11",
        "python3.12": "PYTHON_3_12",
        "python3.13": "PYTHON_3_13",
    }
    return mapping.get(runtime or "python3.12", "PYTHON_3_12")


def _build_env() -> jinja2.Environment:
    """Create the Jinja2 Environment used for Python source rendering."""
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(_TEMPLATES_DIR),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters.update(
        {
            "snake": _snake_case,
            "pascal": _pascal_case,
            "bool_literal": _bool_literal,
            "quote": _quote,
            "route_method": _route_method,
            "route_path": _route_path,
            "runtime_enum": _runtime_enum,
        }
    )
    return env


def render_project(spec: ArchitectureSpec) -> dict[str, str]:
    """Render a full Python CDK project as {relative_path: source_text}."""
    env = _build_env()
    stack_class = f"{_pascal_case(spec.project_name)}Stack"

    service_blocks = [
        env.get_template(registry.template_for(service.type)).render(
            logical_id=service.logical_id,
            config=service.config,
        )
        for service in spec.services
    ]

    files: dict[str, str] = {}
    for output_path, template_path in registry.PROJECT_TEMPLATES.items():
        files[output_path] = env.get_template(template_path).render(
            project_name=spec.project_name,
            stack_class=stack_class,
            services=spec.services,
            budget_monthly_usd=spec.budget_monthly_usd,
        )

    files["cloudcompass_generated/__init__.py"] = ""
    files["cloudcompass_generated/generated_stack.py"] = env.get_template(
        "project/stack.py.j2"
    ).render(
        project_name=spec.project_name,
        stack_class=stack_class,
        services=spec.services,
        rendered_service_blocks=service_blocks,
    )
    return dict(sorted(files.items()))
