"""Offline exact-source tests for Standard 150 promotion rollback preflight.

The owner-comment workflow's existing rollback function restores one revision
to 100%. Preflight must not approve that mutation when the preexisting live
traffic is split, incomplete or insufficiently identified. This executes only
the extracted Python discovery code against synthetic Cloud Run JSON; there
are no cloud calls, credentials or customer scans.
"""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/fixlist-cloud-operator.yml"
SOURCE_SHA = "a" * 40
CANDIDATE = "worker-00125-candidate"
PRIOR = "worker-00100-prior"


def discovery_python() -> str:
    source = WORKFLOW.read_text(encoding="utf-8")
    begin = (
        '          readarray -t resolved < <(python3 - "$SOURCE_SHA" '
        "/tmp/revisions.json /tmp/service-before.json <<'PY'\n"
    )
    end = "\n          PY\n"
    assert source.count(begin) == 1
    body = source.split(begin, 1)[1].split(end, 1)[0]
    assert "rollback = live[0][1]" in body
    return textwrap.dedent(body) + "\n"


def resolve(tmp_path: Path, traffic: list[dict]):
    revisions = [{
        "metadata": {"name": CANDIDATE, "creationTimestamp": "2026-11-13T00:00:00Z"},
        "spec": {
            "containers": [{"env": [
                {"name": "FIXLIST_WORKER_SOURCE_SHA", "value": SOURCE_SHA}
            ]}],
            "containerConcurrency": 1,
            "timeoutSeconds": 480,
        },
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }]
    revisions_path = tmp_path / "revisions.json"
    service_path = tmp_path / "service.json"
    revisions_path.write_text(json.dumps(revisions), encoding="utf-8")
    service_path.write_text(json.dumps({"status": {"traffic": traffic}}), encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-c", discovery_python(), SOURCE_SHA,
         str(revisions_path), str(service_path)],
        capture_output=True, text=True, check=False, timeout=8,
    )


@pytest.mark.parametrize("traffic", [
    [{"revisionName": PRIOR, "percent": 100}],
    [{"revisionName": PRIOR, "percent": 100},
     {"revisionName": CANDIDATE, "percent": 0, "tag": "staging"}],
    [{"revisionName": PRIOR, "percent": "100"},
     {"revisionName": "ignored-tag", "percent": 0}],
])
def test_one_named_100_percent_rollback_is_preserved(tmp_path, traffic):
    result = resolve(tmp_path, traffic)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines() == [CANDIDATE, PRIOR]


@pytest.mark.parametrize("traffic", [
    [{"revisionName": PRIOR, "percent": 60},
     {"revisionName": "worker-another", "percent": 40}],
    [{"revisionName": PRIOR, "percent": 50},
     {"revisionName": PRIOR, "percent": 50}],
    [{"revisionName": PRIOR, "percent": 80}, {"percent": 20}],
    [{"revisionName": PRIOR, "percent": 99}],
    [{"revisionName": PRIOR, "percent": 100},
     {"revisionName": "unexpected", "percent": 1}],
    [{"revisionName": PRIOR, "percent": 100},
     {"revisionName": "invalid", "percent": -1}],
    [{"percent": 100}],
    [],
])
def test_lossy_or_ambiguous_rollback_preflight_is_refused(tmp_path, traffic):
    result = resolve(tmp_path, traffic)
    assert result.returncode != 0
    assert "Rollback preflight requires one named revision at exactly 100% traffic" in result.stderr
    assert result.stdout.strip() == ""


def test_candidate_already_live_still_refused(tmp_path):
    result = resolve(tmp_path, [{"revisionName": CANDIDATE, "percent": 100}])
    assert result.returncode != 0
    assert "Candidate already receives 100% traffic" in result.stderr


def test_preflight_is_before_first_candidate_tag_mutation():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert source.index("Rollback preflight requires one named revision at exactly 100% traffic") < (
        source.index("      - name: Tag the exact zero-traffic candidate")
    )
