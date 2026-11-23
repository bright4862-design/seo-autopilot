"""Source-only composition checks for the two Standard 150 draft safety lanes.

#560: guarded owner promotion/rollback, seven-route package attestation, signed drain.
#548: serving-worker provenance and customer-access readback.
Do not dispatch any cloud operation here; these are regression assertions on code.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_direct_promotion_refused_and_serving_route_bound():
    workflow = (ROOT / ".github/workflows/fixlist-cloud-operator.yml").read_text()
    step = workflow.split("      - name: Run allowlisted worker operation\n", 1)[1].split(
        "      - name: Build isolated Standard 150 worker candidate\n", 1
    )[0]
    deny = step.index('if [[ "$OPERATION" == "promote-worker" ]]; then')
    select = step.index('if [[ "$OPERATION" == "verify-worker-routes" ]]; then')
    assert deny < select, "direct promotion must be refused before read-only routing"
    assert "Refusing direct promotion:" in step
    assert "scripts/resolve_serving_worker_revision.py" in step
    assert 'export TARGET_REVISION="$route_revision"' in step
    assert 'after_revision="$(get_serving_revision)"' in step
    assert '[[ "$after_revision" == "$route_revision" ]]' in step


def test_promotion_retains_owner_pinning_and_drain_gate():
    workflow = (ROOT / ".github/workflows/fixlist-cloud-operator.yml").read_text()
    owner = workflow.split("  promote-staged-worker-on-owner-comment:\n", 1)[1].split(
        "\n  ", 1
    )[0]
    assert 'approved_revision="${approval[2]}"' in owner
    assert 'approved_image_digest="${approval[3]}"' in owner
    assert 'approved_barrier_generation="${approval[4]}"' in owner
    assert "VERIFY_OWNER_DEBUG_RUNTIME=1" in owner
    assert "verify-base44-functions.sh" in owner
    assert "OPERATION: verify-zero-admission-obligations" in owner
    assert "--to-revisions" in owner


def test_runtime_provenance_and_signed_barrier_are_both_checked():
    operator = (ROOT / "scripts/fixlist-cloud-operator.sh").read_text()
    assert "verify_worker_build_provenance.py" in operator
    assert "live_worker_revision" in operator
    assert "Barrier envelope disagrees with signed drain snapshot" in operator
    assert 'assert_standard150_promotion_record.py" --source-sha "$SOURCE_SHA" --worker-promotion' in operator
