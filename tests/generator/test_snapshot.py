"""Snapshot tests: render each canonical example spec and assert the output
matches a committed snapshot under snapshots/.

Because rendering is deterministic, byte-for-byte snapshot comparison is the
right tool. Regenerate snapshots intentionally (e.g. UPDATE_SNAPSHOTS=1) when a
template legitimately changes.

TODO(diego): implement once render_project() and the first template exist.
"""
import pytest

pytestmark = pytest.mark.skip(reason="TODO(diego): scaffold only — implement after first template")


def test_s3_only_matches_snapshot():
    """generate_cdk_project(s3_only.json) == snapshots/s3_only/..."""
    raise NotImplementedError


def test_rendering_is_deterministic():
    """Rendering the same spec twice yields identical output."""
    raise NotImplementedError
