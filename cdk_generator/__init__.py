"""CloudCompass — Workstream 2: deterministic CDK generator.

This package renders Python CDK *source text* for the end user's recommended
architecture. It is a PRODUCT FEATURE, not infrastructure we deploy.

  - Input:  a validated architecture spec (see schema/architecture_spec.schema.json)
  - Output: Python CDK source files as in-memory strings (project_id -> {path: text})

Rendering is DETERMINISTIC (Jinja2 templates, no LLM in the loop) so it is
snapshot-testable. WS1's agents select the template + fill parameters; this
package only renders.

Do NOT confuse the generated skeleton with cdk_app/ (the app's own deployable
CDK). They are different artifacts and live in different packages.
"""

__all__ = ["generate_cdk_project"]

from cdk_generator.tool import generate_cdk_project
