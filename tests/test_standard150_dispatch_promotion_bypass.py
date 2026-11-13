"""Prevent the manual Cloud Operator path bypassing guarded worker promotion.

Only the dedicated owner-comment path performs tagged candidate runtime
attestation *before* promotion and authenticated post-check with rollback.
These tests execute the workflow's real dispatch Bash body with a harmless stub;
no cloud commands or customer scans are made.
"""
import os
import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/fixlist-cloud-operator.yml"
STEP = "      - name: Run allowlisted worker operation"
NEXT_STEP = "      - name: Build isolated Standard 150 worker candidate"


def dispatch_body() -> str:
    source = WORKFLOW.read_text()
    assert source.count(STEP) == 1
    section = source.split(STEP, 1)[1].split(NEXT_STEP, 1)[0]
    assert "        run: |\n" in section
    return textwrap.dedent(section.split("        run: |\n", 1)[1]).strip() + "\n"


def run_dispatch(tmp_path: Path, operation: str):
    (tmp_path / "scripts").mkdir()
    sentinel = tmp_path / "operator-invoked"
    script = tmp_path / "scripts/fixlist-cloud-operator.sh"
    script.write_text(f'#!/usr/bin/env bash\nprintf "called" > "{sentinel}"\n')
    script.chmod(0o755)
    env = dict(os.environ, OPERATION=operation)
    completed = subprocess.run(
        ["bash", "-c", dispatch_body()], cwd=tmp_path, env=env,
        capture_output=True, text=True, timeout=5, check=False,
    )
    return completed, sentinel.exists()


def test_manual_promotion_is_not_an_offered_dispatch_choice():
    source = WORKFLOW.read_text()
    dispatch_choices = source.split("        options:\n", 1)[1].split("      revision:", 1)[0]
    assert "          - promote-worker\n" not in dispatch_choices
    assert "          - rollback-worker\n" in dispatch_choices


def test_legacy_direct_promotion_input_refuses_before_operator_script(tmp_path):
    result, reached_operator = run_dispatch(tmp_path, "promote-worker")
    assert result.returncode == 2
    assert not reached_operator
    assert "Refusing direct promotion" in result.stderr


def test_emergency_rollback_still_reaches_existing_operator(tmp_path):
    result, reached_operator = run_dispatch(tmp_path, "rollback-worker")
    assert result.returncode == 0, result.stderr
    assert reached_operator


def test_guarded_owner_comment_still_attests_before_and_after_promoting():
    source = WORKFLOW.read_text()
    gated = source.split(
        "      - name: Verify candidate runtime release identity before promotion", 1
    )[1].split("      - name: Publish exact promotion status", 1)[0]
    assert gated.index("OPERATION: verify-worker-runtime-revision") < gated.index(
        "export OPERATION=promote-worker"
    )
    assert gated.index("export OPERATION=promote-worker") < gated.index(
        "if ! OPERATION=verify-worker-runtime-revision"
    )
    assert "rollback() {" in gated
    assert "rollback" in gated.split(
        "if ! OPERATION=verify-worker-runtime-revision", 1
    )[1]
