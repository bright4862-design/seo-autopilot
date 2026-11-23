"""Hermetic release-control test: rollback must not erase another operator's routing.

Only synthetic Cloud Run service JSON. No network, credentials or live traffic.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/assert_standard150_rollback_ownership.py"
sys.path.insert(0, str(ROOT / "scripts"))
from assert_standard150_rollback_ownership import check_ownership

CANDIDATE, PRIOR, FOREIGN = "worker-125", "worker-100", "worker-999"


def service(desired, observed):
    return {
        "spec": {"traffic": [{"revisionName": r, "percent": pct} for r, pct in desired]},
        "status": {"traffic": [{"revisionName": r, "percent": pct} for r, pct in observed]},
    }


@pytest.mark.parametrize(("desired", "observed", "expected"), [
    ([(PRIOR, 100)], [(PRIOR, 100)], "ALREADY_RESTORED"),
    ([(CANDIDATE, 100)], [(CANDIDATE, 100)], "ALLOW_RESTORE"),
    ([(CANDIDATE, 100)], [(PRIOR, 100)], "ALLOW_RESTORE"),
    ([(CANDIDATE, 70), (PRIOR, 30)], [(PRIOR, 100)], "ALLOW_RESTORE"),
])
def test_single_owner_or_in_flight_promotion(desired, observed, expected):
    assert check_ownership(service(desired, observed), CANDIDATE, PRIOR) == expected


@pytest.mark.parametrize(("desired", "observed"), [
    ([(FOREIGN, 100)], [(FOREIGN, 100)]),
    ([(FOREIGN, 100)], [(CANDIDATE, 100)]),
    ([(CANDIDATE, 100)], [(FOREIGN, 100)]),
    ([(CANDIDATE, 50), (FOREIGN, 50)], [(CANDIDATE, 100)]),
    ([(CANDIDATE, 100)], [(CANDIDATE, 60), (CANDIDATE, 40)]),
    ([(CANDIDATE, 99)], [(CANDIDATE, 100)]),
    ([(CANDIDATE, 100)], [(CANDIDATE, 100), (FOREIGN, 1)]),
    ([{"latestRevision": True, "percent": 100}], [(CANDIDATE, 100)]),
])
def test_competing_or_ambiguous_traffic_is_refused(desired, observed):
    with pytest.raises(ValueError):
        check_ownership(service(desired, observed), CANDIDATE, PRIOR)


def test_cli_refuses_foreign_operator_without_touching_traffic(tmp_path):
    path = tmp_path / "service.json"
    path.write_text(json.dumps(service([(FOREIGN, 100)], [(FOREIGN, 100)])))
    result = subprocess.run(
        [sys.executable, str(HELPER), "--service-json", str(path),
         "--candidate", CANDIDATE, "--prior", PRIOR],
        capture_output=True, text=True, timeout=5,
    )
    assert result.returncode == 2
    assert "ROLLBACK_CONFLICT" in result.stderr
    assert "ALLOW_RESTORE" not in result.stdout


def test_rollback_ownership_uses_real_workflow_before_update_traffic():
    workflow = (ROOT / ".github/workflows/fixlist-cloud-operator.yml").read_text()
    start = workflow.index("      - name: Promote exact candidate with automatic rollback on failed post-check")
    end = workflow.index("      - name: Publish exact promotion status", start)
    section = workflow[start:end]
    assert 'scripts/assert_standard150_rollback_ownership.py' in section
    assert section.index("assert_standard150_rollback_ownership.py") < section.index("--to-revisions=\"$ROLLBACK_REVISION=100\"")
    assert "ROLLBACK_UNVERIFIED: ownership conflict" in section
    guard = (ROOT / "scripts/assert_standard150_promotion_record.py").read_text()
    assert '"scripts/assert_standard150_rollback_ownership.py"' in guard
