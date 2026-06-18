import json
from pathlib import Path

import jsonschema

from cdk_generator import registry
from cdk_generator.generator import load_schema

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "cdk_generator" / "schema" / "examples"


def test_examples_validate_against_schema():
    schema = load_schema()
    for example_path in sorted(EXAMPLES_DIR.glob("*.json")):
        raw = json.loads(example_path.read_text(encoding="utf-8"))
        jsonschema.validate(raw, schema)


def test_schema_enum_matches_registry():
    schema = load_schema()
    service_enum = schema["$defs"]["service"]["properties"]["type"]["enum"]
    assert sorted(service_enum) == registry.supported_types()
