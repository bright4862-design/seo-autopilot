"""Owner promotion must validate executing Base44 route bytes after site-source proof.

Tests execute only the actual owner-workflow Bash preflight fragment with inert local
scripts. No Base44, GCP, customer scan or external network activity.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import textwrap

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/fixlist-cloud-operator.yml"
PRE = "      - name: Verify matching Base44 site and executing scanner/customer routes"
POST = "      - name: Resolve the worker's canonical service URL"


def preflight() -> str:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert source.count(PRE) == 1
    assert source.count(POST) == 1
    section = source.split(PRE, 1)[1].split(POST, 1)[0]
    assert source.index(PRE) < source.index("      - name: Promote exact candidate with automatic rollback")
    assert "EXPECTED_SOURCE_SHA: ${{ steps.command.outputs.product_sha }}" in section
    return textwrap.dedent(section.split("        run: |\n", 1)[1]).strip() + "\n"


def fake_script(path: Path, name: str) -> None:
    path.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"printf '%s\\n' '{name}' >> \"$FIXTURE_CALLS\"\n"
        f"if [[ \"${{FAIL_STAGE:-}}\" == '{name}' ]]; then exit 13; fi\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


@pytest.mark.parametrize("failure,expected", [
    ("", ["site", "functions"]),
    ("site", ["site"]),
    ("functions", ["site", "functions"]),
])
def test_preflight_fails_closed_without_mutating_traffic(tmp_path, failure, expected):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    fake_script(scripts / "verify-base44-site.sh", "site")
    fake_script(scripts / "verify-base44-functions.sh", "functions")
    log = tmp_path / "calls"
    env = dict(os.environ, FIXTURE_CALLS=str(log), FAIL_STAGE=failure)
    result = subprocess.run(
        ["bash", "-c", preflight()], cwd=tmp_path, env=env,
        capture_output=True, text=True, timeout=8, check=False,
    )
    assert log.read_text(encoding="utf-8").splitlines() == expected
    assert (result.returncode == 0) == (failure == "")
    assert ("BASE44_PREPROMOTION_RUNTIME_ROUTES_VERIFIED" in result.stdout) == (failure == "")


def test_route_identity_verifier_requires_actual_build_and_activation_ids():
    actual = (ROOT / "scripts/verify-base44-functions.sh").read_text(encoding="utf-8")
    assert 'status" == "405"' in actual
    assert 'actual" == "$expected"' in actual
    assert 'actual_activation" == "$expected_activation"' in actual
    assert "BASE44_FUNCTIONS_SOURCE_VERIFIED" in actual


def test_preflight_uses_fixed_production_app_and_origin():
    body = preflight()
    assert "BASE44_APP_ID=6a498732ec779dfaaeab0e53" in body
    assert "BASE44_FUNCTION_ORIGIN=https://base44.app" in body
    assert body.index("verify-base44-site.sh") < body.index("verify-base44-functions.sh")

def test_owner_diagnostic_is_required_before_traffic(tmp_path):
    """The real pre-promotion Bash must ask for seven packages, not six."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    fake_script(scripts / "verify-base44-site.sh", "site")
    function_script = scripts / "verify-base44-functions.sh"
    function_script.write_text(
        "#!/usr/bin/env bash\\n"
        "set -euo pipefail\\n"
        'printf "%s\\n" "${VERIFY_OWNER_DEBUG_RUNTIME:-missing}" > "$FIXTURE_FLAG"\\n'
        '[[ "${VERIFY_OWNER_DEBUG_RUNTIME:-}" == "1" ]]\\n'
        'printf "%s\\n" "functions" >> "$FIXTURE_CALLS"\\n',
        encoding="utf-8",
    )
    function_script.chmod(0o755)
    log = tmp_path / "calls"
    flag = tmp_path / "owner-flag"
    env = dict(os.environ, FIXTURE_CALLS=str(log), FIXTURE_FLAG=str(flag))
    result = subprocess.run(
        ["bash", "-c", preflight()], cwd=tmp_path, env=env,
        capture_output=True, text=True, timeout=8, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert log.read_text(encoding="utf-8").splitlines() == ["site", "functions"]
    assert flag.read_text(encoding="utf-8").strip() == "1"
    assert "BASE44_PREPROMOTION_RUNTIME_ROUTES_VERIFIED" in result.stdout


def test_promotion_requires_explicit_opt_in_supported_by_verifier():
    gate = preflight()
    verifier = (ROOT / "scripts/verify-base44-functions.sh").read_text(encoding="utf-8")
    assert "VERIFY_OWNER_DEBUG_RUNTIME=1" in gate
    assert 'FUNCTION_ROUTES+=(ownerScanDebugControl)' in verifier
    assert 'VERIFY_OWNER_DEBUG_RUNTIME must be 0 or 1' in verifier
    assert gate.index("verify-base44-site.sh") < gate.index("verify-base44-functions.sh")
