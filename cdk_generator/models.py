"""Parsed, validated representation of an architecture spec.

These dataclasses are the in-memory form the generator works with after the raw
JSON spec has been validated against architecture_spec.schema.json. Keeping a
typed model (instead of passing raw dicts into templates) makes the templates
dumb and the rendering predictable.

SCOPE NOTE: the *shape* of the incoming spec is a shared contract with WS1
(Architecture Designer Agent). Any change to these fields must be mirrored in
the JSON schema and signed off by WS1.

TODO(diego): finalize fields once the schema is locked with WS1.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ServiceSpec:
    """A single AWS service the generated project should provision."""

    type: str          # canonical service key, e.g. "s3_bucket", "lambda_api", "dynamodb_table"
    logical_id: str    # CDK construct id, unique within the project
    config: dict = field(default_factory=dict)  # template-specific parameters
    # TODO(diego): add `depends_on` / relationship modeling once WS1 defines it.


@dataclass(frozen=True)
class ArchitectureSpec:
    """The full, validated input to the generator."""

    project_name: str
    pattern: str                       # e.g. "serverless-web-application"
    services: list[ServiceSpec] = field(default_factory=list)
    deployment_boundary: str = "change-set-only"
    # TODO(diego): budget, region hints, tags, outputs — add as schema firms up.

    @classmethod
    def from_dict(cls, raw: dict) -> "ArchitectureSpec":
        """Build a spec from an already-schema-validated dict.

        NOTE: this does not validate — call validate_spec() (see generator.py)
        first. Kept as a stub until the schema is locked.
        """
        raise NotImplementedError("TODO(diego): map validated dict -> dataclasses")
