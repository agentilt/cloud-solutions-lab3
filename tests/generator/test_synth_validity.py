import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cdk_generator import generate_cdk_project

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "cdk_generator" / "schema" / "examples"


def _load_example(name: str) -> dict:
    return json.loads((EXAMPLES_DIR / name).read_text(encoding="utf-8"))


def test_rendered_files_are_valid_python():
    result = generate_cdk_project(_load_example("bakery.json"))

    for path, source in result["files"].items():
        if path.endswith(".py"):
            compile(source, path, "exec")


@pytest.mark.slow
@pytest.mark.skipif(
    os.environ.get("RUN_SLOW_CDK_TESTS") != "1",
    reason="set RUN_SLOW_CDK_TESTS=1 to run generated project cdk synth",
)
def test_sample_project_cdk_synths(tmp_path):
    result = generate_cdk_project(_load_example("bakery.json"))
    for relative_path, source in result["files"].items():
        destination = tmp_path / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(source, encoding="utf-8")

    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["cdk", "synth"], cwd=tmp_path, check=True)
