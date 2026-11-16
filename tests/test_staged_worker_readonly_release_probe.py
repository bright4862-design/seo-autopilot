"""Zero-traffic candidate attribution and the separate owner-only probe path."""
import json
import os
from pathlib import Path
import shutil
import subprocess
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


def test_revision_specific_canary_survives_shared_candidate_reassignment():
    service = tagged_candidate()
    tag = "canary-00101-zh2"
    url = "https://canary-00101-zh2---fixlist-standard150-worker.example.a.run.app"
    service["status"]["traffic"][1] = {"revisionName": REVISION, "tag": tag, "url": url}
    service["status"]["traffic"].append({"revisionName": "fixlist-standard150-worker-00102-nn7", "tag": "candidate", "url": TAG_URL})
    assert verify_tagged_zero_traffic(service, REVISION, tag=tag) == url


def test_canary_tag_cannot_name_a_different_revision():
    with pytest.raises(CandidateNotIsolated, match="canary_tag_revision_mismatch"):
        verify_tagged_zero_traffic(tagged_candidate(), REVISION, tag="canary-00102-nn7")


def test_canary_url_must_bind_the_exact_tag_and_same_service():
    service = tagged_candidate()
    service["status"]["traffic"][1].update(tag="canary-00101-zh2", url=TAG_URL)
    with pytest.raises(CandidateNotIsolated, match="canary_tag_url_mismatch"):
        verify_tagged_zero_traffic(service, REVISION, tag="canary-00101-zh2")


def test_canary_tag_reassignment_is_rejected():
    service = tagged_candidate()
    service["status"]["traffic"][1].update(tag="canary-00101-zh2", revisionName="fixlist-standard150-worker-00102-nn7")
    with pytest.raises(CandidateNotIsolated, match="canary_tag_reassigned"):
        verify_tagged_zero_traffic(service, REVISION, tag="canary-00101-zh2")


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


def test_source_bound_tag_needs_exact_source_revision_and_zero_traffic():
    source = "a" * 40
    tag = "staged-" + source[:12]
    service = tagged_candidate()
    origin = "https://fixlist-standard150-worker.example.run.app"
    service["status"]["url"] = origin
    url = origin.replace("https://", f"https://{tag}---")
    service["status"]["traffic"].append({"revisionName": REVISION, "tag": tag, "url": url})
    assert verify_tagged_zero_traffic(service, REVISION, tag, source_sha=source) == url
    with pytest.raises(CandidateNotIsolated, match="source_tag_mismatch"):
        verify_tagged_zero_traffic(service, REVISION, tag, source_sha="b" * 40)
    service["status"]["traffic"][-1]["percent"] = 0.5
    with pytest.raises(CandidateNotIsolated, match="candidate_percent_invalid"):
        verify_tagged_zero_traffic(service, REVISION, tag, source_sha=source)


@pytest.mark.parametrize("has_drain_route", [True, False])
def test_worker_route_probe_reads_large_source_without_sigpipe(tmp_path, has_drain_route):
    source_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    source_file = tmp_path / "main.py"
    decorators = '@app.post("/scan-job")\n'
    if has_drain_route:
        decorators += '@app.post("/scan-job-drain")\n'
    # The early match and trailing data larger than a pipe buffer reproduce
    # the Git writer's SIGPIPE when the reader quits at the first match.
    source_file.write_text(decorators + "# padding after the route decorators\n" * 65_536)

    git = tmp_path / "git"
    git.write_text('''#!/bin/bash
if [[ "$1" == show && "$2" == "$PROBE_SHA:scanner-api/app/main.py" ]]; then
  exec cat "$PROBE_SOURCE"
fi
exec "$REAL_GIT" "$@"
''')
    git.chmod(0o755)

    gcloud = tmp_path / "gcloud"
    gcloud.write_text('''#!/bin/bash
case "$1 $2 $3 ${!#}" in
  "config set project test-project") ;;
  "run revisions describe --format=value(spec.containers[0].image)") printf '%s\\n' "$PROBE_IMAGE" ;;
  "run revisions describe --format=json") printf '%s\\n' "$PROBE_REVISION" ;;
  "run revisions describe --format=value(spec.timeoutSeconds)") echo 480 ;;
  "builds list "*) printf '%s\\n' "$PROBE_BUILDS" ;;
  *) exit 99 ;;
esac
''')
    gcloud.chmod(0o755)
    digest = "sha256:" + "a" * 64
    env = {
        **os.environ,
        "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
        "REAL_GIT": shutil.which("git"),
        "PROBE_SOURCE": str(source_file),
        "PROBE_SHA": source_sha,
        "PROBE_IMAGE": "test.example/worker:release-tag",
        # A healthy revision is resolved to immutable bytes even if its spec
        # refers to a tag. The operator now requires this independent JSON.
        "PROBE_REVISION": json.dumps({
            "spec": {"containers": [{"image": "test.example/worker:release-tag"}]},
            "status": {"imageDigest": "test.example/worker@" + digest},
        }),
        "PROBE_BUILDS": json.dumps([{
            "id": "fixture-build-1",
            "status": "SUCCESS",
            "substitutions": {"_RELEASE_SHA": source_sha},
            "results": {"images": [{"name": "test.example/worker:build-tag", "digest": digest}]},
        }]),
        "GCP_PROJECT": "test-project",
        "GCP_REGION": "test-region",
        "CLOUD_RUN_SERVICE": "fixlist-standard150-worker",
        "CLOUD_TASKS_QUEUE": "test-queue",
        "TASKS_INVOKER_SERVICE_ACCOUNT": "test-invoker",
        "TARGET_REVISION": REVISION,
        "OPERATION": "verify-worker-routes",
    }
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/fixlist-cloud-operator.sh")], cwd=ROOT, env=env,
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == (0 if has_drain_route else 1), result.stdout + result.stderr
    if has_drain_route:
        assert "WORKER ROUTES VERIFIED" in result.stdout
    else:
        assert "does NOT declare both durable routes" in result.stdout


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
