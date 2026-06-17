# cdk_generator — Workstream 2 (deterministic CDK generation)

Renders **Python CDK source text** for the end user's recommended architecture.
This is a **product feature**, not infrastructure we deploy — do not confuse it
with `cdk_app/` (the CloudCompass app's own deployable CDK).

## Pipeline

```
raw spec dict (from WS1 Architecture Designer)
  -> validate_spec()      # jsonschema vs schema/architecture_spec.schema.json
  -> ArchitectureSpec     # models.py
  -> render_project()     # generator.py, Jinja2, deterministic
  -> { "<path>": "<source text>" }
```

No LLM in the rendering step → snapshot-testable.

## Layout

```
cdk_generator/
  __init__.py            # exports generate_cdk_project
  tool.py                # clean entry point WS1 wraps as a Strands @tool
  generator.py           # deterministic renderer (validate -> render)
  registry.py            # service type -> template mapping
  models.py              # typed, validated spec
  requirements.txt       # jinja2 + jsonschema (no AWS SDK)
  schema/
    architecture_spec.schema.json   # WS1<->WS2 contract (DRAFT v0)
    examples/            # s3_only, lambda_api, bakery
  templates/
    project/             # app.py, cdk.json, requirements.txt, README, stack
    services/            # s3_bucket, lambda_api, dynamodb_table (canonical 3)
tests/generator/
  test_schema_contract.py
  test_snapshot.py
  test_synth_validity.py
  snapshots/
```

## Status

Scaffolding only. Implementation order (see `diego-part.md`):

1. Lock the input schema with WS1.
2. Implement `render_project()` + the `s3_bucket` template end-to-end with a snapshot test.
3. Add the `cdk synth` validity check.
4. Expand to `lambda_api` and `dynamodb_table`.

## Contract note

`schema/architecture_spec.schema.json` is a **shared contract with WS1**. The
service-type enum there MUST stay in sync with `registry.supported_types()`
(enforced by `test_schema_contract.py`). Any schema change needs WS1 sign-off.
