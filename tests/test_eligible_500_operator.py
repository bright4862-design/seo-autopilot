import hashlib
import hmac
import json
import re
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
OPERATOR = (ROOT / "scripts/fixlist-cloud-operator.sh").read_text()
SOURCE = "a" * 40
BUILD = "b" * 64
SNAPSHOT_LABEL = "fixlist-admission-drain-snapshot-v1"
TEST_KEY = b"offline operator fixture key"


def _operator_function(name, args, directory):
    definition = re.split(
        r"\n}\n(?=\n(?:[a-z][a-z0-9_]+\(\) \{|case ))", OPERATOR.split(f"{name}() {{", 1)[1], maxsplit=1,
    )[0]
    script = f"set -euo pipefail\n{name}() {{{definition}\n}}\n" + args
    return subprocess.run(["bash", "-c", script], cwd=directory, capture_output=True, text=True, timeout=10)


def _setting_values():
    return f"""
SOURCE_SHA={SOURCE} ACCEPTANCE_SOURCE_SHA={SOURCE} ACCEPTANCE_LAUNCHER_BUILD_ID={BUILD}
BARRIER_EXPECTED_GENERATION=15 BARRIER_EXPECTED_PRIOR_MODE=open
ACCEPTANCE_COHORT_ID=eligible-first ACCEPTANCE_RELEASE_ID=paid-500-release
ACCEPTANCE_OWNER_USER_IDS= ACCEPTANCE_EXPIRES_AT=1900000000
ACCEPTANCE_TOTAL_CLAIM_BUDGET=10 ACCEPTANCE_PER_OWNER_CLAIM_BUDGET=2
CUTOVER_REASON=scope CHANGE_TICKET=PR-581
LEGACY_ACCESS= LEGACY_ACCESS_SHA256= LEGACY_ACCESS_PREFLIGHT=
"""


def test_start_payload_scopes_eligible_500_without_an_owner_roster(tmp_path):
    outcome = _operator_function("write_acceptance_payload", _setting_values() + """
write_acceptance_payload body.json start_eligible_500
""", tmp_path)
    assert outcome.returncode == 0, outcome.stderr
    payload = json.loads((tmp_path / "body.json").read_text())
    assert payload["operation"] == "start_eligible_500"
    assert payload["intended_prior"] == {"mode": "open", "generation": 15}
    assert payload["public_500"] == {
        "cohort_id": "eligible-first", "release_id": "paid-500-release",
        "source_sha": SOURCE, "required_launcher_build_id": BUILD,
        "expires_at": 1900000000, "total_claim_budget": 10, "per_owner_claim_budget": 2,
    }


def test_hold_payload_binds_source_and_open_generation(tmp_path):
    outcome = _operator_function("write_barrier_payload", _setting_values() + """
write_barrier_payload hold_eligible_500 body.json
""", tmp_path)
    assert outcome.returncode == 0, outcome.stderr
    payload = json.loads((tmp_path / "body.json").read_text())
    assert payload == {
        "operation": "hold_eligible_500", "reason": "scope", "change_ticket": "PR-581",
        "intended_prior": {"mode": "open", "generation": 15},
        "cohort_id": "eligible-first", "source_sha": SOURCE,
    }


def test_local_hold_works_from_the_clean_merged_serving_source(tmp_path):
    guard = tmp_path / "scripts/lib/release-source-guard.sh"
    guard.parent.mkdir(parents=True)
    guard.write_text('fixlist_require_merged_checkout() { [[ "$1" == "." && "$2" == "$SOURCE_SHA" ]]; }\n')
    outcome = _operator_function("operate_eligible_500", _setting_values() + """
REPO_ROOT=. GITHUB_ACTIONS=false
require_exact_main_owner_source() { return 99; }
require_barrier_inputs() { :; }
require_confirmation() { [[ "$1" == "HOLD-ELIGIBLE-500:$SOURCE_SHA:15:eligible-first" ]]; }
call_barrier_operator() { [[ "$1" == "hold_eligible_500" && "$2" == "/ops/barrier/eligible-500/hold" ]]; }
parse_barrier_response() {
  [[ "$1" == "hold_eligible_500" ]]
  BARRIER_GENERATION=16 BARRIER_MODE=open BARRIER_SNAPSHOT_ID=snapshot_held
}
operate_eligible_500 hold
""", tmp_path)
    assert outcome.returncode == 0, outcome.stderr
    assert "action=hold generation=16" in outcome.stdout
    assert "snapshot=snapshot_held" in outcome.stdout


@pytest.mark.parametrize("action", ["start", "hold"])
@pytest.mark.parametrize("wrong_binding", [None, "500", "150"])
def test_eligible_500_requires_the_exact_signed_boundary(tmp_path, action, wrong_binding):
    operation = f"{action}_eligible_500"
    starting = action == "start"
    barrier = {"mode": "open", "generation": 16, "current_snapshot_id": "snapshot_example", "claim_sequence": 3}
    boundary = {
        "state": "configured" if starting else "held", "page_cap": 500, "cohort_id": "eligible-first",
        "release_id": "paid-500-release", "source_sha": ("c" * 40) if wrong_binding == "500" and not starting else SOURCE,
        "required_launcher_build_id": ("c" * 64) if wrong_binding == "500" and starting else BUILD,
        "expires_at": 1900000000, "total_claim_budget": 10, "per_owner_claim_budget": 2,
        "total_claims_used": 0,
    }
    boundaries = {"public_500": boundary}
    if wrong_binding != "150":
        boundaries["public_150"] = {"state": "configured", "page_cap": 150, "cohort_id": "public-first"}
    snapshot = {
        "version": "admission_eligible_500_snapshot_v1", "snapshot_id": "snapshot_example",
        "barrier": barrier, "boundary": boundaries, "drain_ready": False,
    }
    key = hmac.new(TEST_KEY, SNAPSHOT_LABEL.encode(), hashlib.sha256).digest()
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    snapshot["proof"] = hmac.new(key, canonical, hashlib.sha256).hexdigest()
    (tmp_path / "operator-key").write_bytes(TEST_KEY)
    (tmp_path / "response.json").write_text(json.dumps({
        "success": True, "operation": operation, "barrier": barrier,
        "eligible_500_snapshot": snapshot,
    }))
    outcome = _operator_function("parse_barrier_response", _setting_values() + f"""
OPERATOR_TMP=. BARRIER_RESPONSE_FILE=response.json
ADMISSION_DRAIN_SNAPSHOT_DERIVATION_LABEL={SNAPSHOT_LABEL}
parse_barrier_response {operation}
printf '%s %s\\n' "$BARRIER_MODE" "$BARRIER_GENERATION"
""", tmp_path)
    if wrong_binding:
        assert outcome.returncode != 0
        expected = "Standard 150 boundary" if wrong_binding == "150" else ("launcher" if starting else "source")
        assert expected in outcome.stderr
    else:
        assert outcome.returncode == 0, outcome.stderr
        assert outcome.stdout.strip() == "open 16"
