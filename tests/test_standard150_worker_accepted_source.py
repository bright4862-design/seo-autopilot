"""Acceptance is bound to the worker image bytes, not just a Git ancestor.

Hermetic temporary Git histories only. No cloud, customer scan or signing calls.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts.assert_standard150_promotion_record import (
    PromotionRecordError,
    verify_promotion_record,
)


@pytest.fixture
def accepted_history(tmp_path: Path):
    root = tmp_path

    def write(name: str, value: str):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")

    def git(*args: str) -> str:
        return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()

    def commit() -> str:
        git("add", ".")
        git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
            "commit", "-qm", "source")
        return git("rev-parse", "HEAD")

    git("init", "-q")
    write("scanner-api/app/main.py", "print('reviewed worker')\n")
    write("Dockerfile", "FROM python:3.12-slim\n")
    write("scanner-api/Dockerfile", "FROM python:3.12-slim\n")
    write("scanner-api/requirements.txt", "fastapi==0.115.6\n")
    write("data/cross-runtime-release-components.json", "{}\n")
    write("scripts/staged_candidate_cloudbuild.py", "print('source verified')\n")
    write("scripts/verify-fixlist-static-egress-canary.sh", "#!/bin/bash\n")
    write("cloudbuild.durable-worker.yaml", "steps: []\n")
    write("cloudbuild.durable-worker-static-egress-canary.yaml", "steps: []\n")
    write("scripts/build-worker-candidate.sh", "#!/bin/bash\n")
    write("scripts/assert_standard150_promotion_record.py", "# immutable release gate\n")
    write("scripts/fixlist-cloud-operator.sh", 'python3 assert_standard150_promotion_record.py --worker-promotion\n')
    write("scripts/lib/release-source-guard.sh", "# exact main is required\n")
    write(".github/workflows/fixlist-cloud-operator.yml", "name: trusted worker operator\n")
    accepted = commit()
    components = {"scanner_version": "fixture_v1"}
    fingerprint = hashlib.sha256(
        json.dumps(components, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]
    write("docs/accepted.md", "# Reviewed and accepted source\n")
    write("data/beta-crawler-revision.json", json.dumps({
        "status": "frozen_beta",
        "git_commit": accepted,
        "acceptance_report": "docs/accepted.md",
        "component_versions": components,
        "fingerprint": fingerprint,
    }))
    current = commit()
    return root, write, commit, current, fingerprint


def test_accepted_ancestor_with_only_manifest_and_report_remains_eligible(accepted_history):
    root, _, _, current, fingerprint = accepted_history
    assert verify_promotion_record(root, current, worker_promotion=True) == fingerprint


def test_a_new_document_after_acceptance_does_not_require_worker_refreeze(accepted_history):
    root, write, commit, _, fingerprint = accepted_history
    write("docs/release-operator-note.md", "Reviewed note only\n")
    assert verify_promotion_record(root, commit(), worker_promotion=True) == fingerprint


@pytest.mark.parametrize("changed_path", [
    "scanner-api/app/main.py",
    "Dockerfile",
    "scanner-api/Dockerfile",
    "scanner-api/requirements.txt",
    "data/cross-runtime-release-components.json",
    "scripts/staged_candidate_cloudbuild.py",
    "scripts/verify-fixlist-static-egress-canary.sh",
    "cloudbuild.durable-worker.yaml",
    "cloudbuild.durable-worker-static-egress-canary.yaml",
    "scripts/build-worker-candidate.sh",
    "scripts/assert_standard150_promotion_record.py",
    "scripts/fixlist-cloud-operator.sh",
    "scripts/lib/release-source-guard.sh",
    ".github/workflows/fixlist-cloud-operator.yml",
])
def test_post_acceptance_worker_change_cannot_reuse_old_acceptance(
    accepted_history, changed_path
):
    root, write, commit, _, fingerprint = accepted_history
    write(changed_path, "new, unaccepted runtime or build bytes\n")
    newer = commit()

    # Baseline: the old metadata-only predicate accepts this descendant.
    assert verify_promotion_record(root, newer) == fingerprint

    # The actual traffic-promotion mode now rejects its changed worker source.
    with pytest.raises(PromotionRecordError, match="worker_source_differs_from_accepted_commit"):
        verify_promotion_record(root, newer, worker_promotion=True)


def test_rollback_does_not_acquire_new_worker_promotion_gate():
    operator = Path("scripts/fixlist-cloud-operator.sh").read_text(encoding="utf-8")
    promote = operator.split("promote_revision() {", 1)[1].split("\n}", 1)[0]
    assert 'if [[ "$OPERATION" == "promote-worker" ]]; then' in promote
    assert 'assert_standard150_promotion_record.py" --source-sha "$SOURCE_SHA" --worker-promotion' in promote
    assert "rollback-worker)" in operator


def test_accepted_record_validation_remains_required_before_worker_diff(accepted_history):
    root, write, commit, _, _ = accepted_history
    record_path = root / "data/beta-crawler-revision.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["status"] = "candidate"
    write("data/beta-crawler-revision.json", json.dumps(record))
    candidate = commit()
    with pytest.raises(PromotionRecordError, match="release_not_accepted_candidate"):
        verify_promotion_record(root, candidate, worker_promotion=True)


def test_dropping_the_worker_promotion_flag_cannot_reuse_old_acceptance(accepted_history):
    root, write, commit, _, fingerprint = accepted_history
    # The operator invokes this script, so an edit removing its new flag would
    # silently restore the metadata-only behavior of the previous launcher.
    write("scripts/fixlist-cloud-operator.sh",
          "python3 assert_standard150_promotion_record.py --source-sha ${SOURCE_SHA}\\n")
    changed = commit()
    assert verify_promotion_record(root, changed) == fingerprint  # previous baseline
    with pytest.raises(PromotionRecordError, match="worker_source_differs_from_accepted_commit"):
        verify_promotion_record(root, changed, worker_promotion=True)
