from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def test_provider_lab_unittest_suite() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "experiments/provider_lab/tests",
            "-p",
            "test_*.py",
        ],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, (
        "Provider Lab isolated unittest suite failed.\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
