"""Validity check: the GENERATED skeleton must be syntactically valid Python
and should `cdk synth` on a sample spec.

Two tiers (cheap -> expensive):
  1. compile() every rendered .py file (fast, no AWS, always run in CI).
  2. write the project to a temp dir and run `cdk synth` (slower; requires the
     CDK CLI + node — gate behind a marker / env so unit runs stay fast).

Success for the user-facing skeleton = syntactically valid + structurally sane.
It does NOT need to deploy in our account (see diego-part.md).

TODO(diego): implement once render_project() exists.
"""
import pytest

pytestmark = pytest.mark.skip(reason="TODO(diego): scaffold only — implement after renderer")


def test_rendered_files_are_valid_python():
    """compile() each generated .py file — no SyntaxError."""
    raise NotImplementedError


@pytest.mark.slow
def test_sample_project_cdk_synths(tmp_path):
    """Write a rendered project to tmp_path and assert `cdk synth` exits 0."""
    raise NotImplementedError
