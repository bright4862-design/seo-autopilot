"""Zero-traffic candidate attribution and the separate owner-only probe path."""
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.assert_tagged_zero_traffic_worker import (
    CandidateNotIsolated,
    verify_tagged_zero_traffic,
)

REVISION = "fixlist-standard150-worker-00101-zh2"
SERVING = "fixlist-standard150-worker-00097-lvl"
TAG_URL = "https://candidate---fixlist-standard150-worker.example.a.run.app"


def tagged_candidate():
    return {
        "status": {
            "url": "https://fixlist-standard150-worker.example.a.run.app",
            "traffic": [
                {"revisionName": SERVING, "percent": 100},
                {"revisionName": REVISION, "percent": 0, "tag": "candidate", "url": TAG_URL},
            ],
        }
    }


def test_exact_tagged_candidate_at_zero_percent_passes():
    assert verify_tagged_zero_traffic(tagged_candidate(), REVISION) == TAG_URL


@pytest.mark.parametrize(("modifier", "failure"), [
    (lambda x: x["status"]["traffic"][1].update(percent=1), "candidate_receives_traffic"),
    (lambda x: x["status"]["traffic"][1].update(percent=100), "candidate_receives_traffic"),
    (lambda x: x["status"]["traffic"][1].pop("tag"), "candidate_tag_missing_or_ambiguous"),
    (lambda x: x["status"]["traffic"][1].pop("url"), "candidate_tag_url_missing"),
    (lambda x: x["status"]["traffic"][1].update(url="http://not-https"), "candidate_tag_url_missing"),
    (lambda x: x["status"]["traffic"].pop(), "candidate_not_addressable"),
])
def test_wrong_or_unaddressable_candidate_fails(modifier, failure):
    service = tagged_candidate()
    modifier(service)
    with pytest.raises(CandidateNotIsolated, match=failure):
        verify_tagged_zero_traffic(service, REVISION)


def test_stale_default_revision_fails_even_if_it_matches_a_tag():
    with pytest.raises(CandidateNotIsolated, match="candidate_not_addressable"):
        verify_tagged_zero_traffic(tagged_candidate(), "fixlist-standard150-worker-00011-v7m")


def test_serving_revision_cannot_be_substituted_for_candidate():
    with pytest.raises(CandidateNotIsolated, match="candidate_receives_traffic"):
        verify_tagged_zero_traffic(tagged_candidate(), SERVING)


def test_malformed_revision_fails():
    with pytest.raises(CandidateNotIsolated, match="revision_not_exact"):
        verify_tagged_zero_traffic(tagged_candidate(), "../../worker")


def test_workflow_separates_tag_mutation_from_read_only_candidate_probe():
    workflow = (ROOT / ".github/workflows/fixlist-cloud-operator.yml").read_text()
    assert "\n          - tag-worker-candidate\n" in workflow
    assert "\n          - verify-staged-worker-release\n" in workflow
    start = workflow.index("      - name: Verify exact tagged zero-traffic worker identity (read only)")
    end = workflow.index("      - name: Run allowlisted worker operation", start)
    probe = workflow[start:end]
    assert 'python3 scripts/assert_tagged_zero_traffic_worker.py' in probe
    assert "OPERATION=verify-worker-routes" in probe
    assert "OPERATION=verify-worker-runtime-revision" in probe
    assert "SOURCE_SHA: ${{ github.sha }}" in probe
    assert "FIXLIST_WORKER_ID_TOKEN" in probe
    assert 'export FIXLIST_WORKER_PROBE_URL="${candidate_check##* tag_url=}"' in probe
    assert "candidate_check=" in probe
    for forbidden in ["update-traffic", "--update-tags", "promote-worker", "queues pause", "queues resume"]:
        assert forbidden not in probe
    assert "inputs.operation != 'verify-staged-worker-release'" in workflow
