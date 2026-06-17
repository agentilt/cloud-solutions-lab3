"""Contract tests: every example spec must satisfy architecture_spec.schema.json,
and the schema's allowed service types must match registry.supported_types().

This is the WS1<->WS2 guardrail — if WS1 emits a spec shape we don't accept, or
the schema and the template registry drift apart, these tests fail loudly.

TODO(diego): implement once the schema is locked. Skipped for now.
"""
import pytest

pytestmark = pytest.mark.skip(reason="TODO(diego): scaffold only — implement after schema lock")


def test_examples_validate_against_schema():
    """Each file in schema/examples/ validates against the schema."""
    raise NotImplementedError


def test_schema_enum_matches_registry():
    """schema service `type` enum == registry.supported_types() (no drift)."""
    raise NotImplementedError
