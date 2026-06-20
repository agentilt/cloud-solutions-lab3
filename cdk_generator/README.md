# cdk_generator

Deterministic Python CDK project generation for CloudCompass Builder.

This package is a product feature: it renders the CDK project handed back to the
end user. It is separate from `cdk_app/`, which deploys CloudCompass itself.

## Pipeline

```text
raw architecture spec
  -> JSON Schema validation
  -> ArchitectureSpec dataclasses
  -> Jinja2 templates
  -> { "relative/path": "source text" }
```

The renderer is deterministic and does not call an LLM. That makes it suitable
for contract tests and byte-stable artifacts.

## Supported MVP Service Types

- `s3_bucket`
- `lambda_api`
- `dynamodb_table`

CloudFront, Cognito, SES, and richer service relationships are future catalog
expansions. The current scope intentionally preserves Person 2's contract and
keeps the generated project small enough for a reliable lab demo.

## Public Entry Point

```python
from cdk_generator import generate_cdk_project

result = generate_cdk_project(architecture_spec)
```

Return shape:

```python
{
    "project_name": "online-bakery",
    "files": {"app.py": "..."},
    "warnings": ["..."],
}
```
