"""Executable real-Git source-delta tests, intentionally offline and harmless."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import assert_standard150_promotion_record as gate


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def commit(root: Path, label: str) -> str:
    git(root, "add", "-A")
    git(root, "commit", "-qm", label)
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def release_history(tmp_path: Path):
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.name", "Fixture")
    git(tmp_path, "config", "user.email", "fixture@example.invalid")
    scanner = tmp_path / "scanner-api/app/scanner.py"
    scanner.parent.mkdir(parents=True)
    scanner.write_text('VERSION = "accepted"\n')
    accepted = commit(tmp_path, "A: accepted source")

    (tmp_path / "data").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/accepted.md").write_text("# Synthetic report\n")
    components = {"scanner_version": "accepted", "sampling_version": "v7"}
    fingerprint = hashlib.sha256(
        json.dumps(components, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]
    record = {"status": "frozen_beta", "git_commit": accepted,
              "acceptance_report": "docs/accepted.md",
              "component_versions": components, "fingerprint": fingerprint}
    (tmp_path / "data/beta-crawler-revision.json").write_text(json.dumps(record))
    frozen = commit(tmp_path, "B: frozen metadata and acceptance report")
    return tmp_path, scanner, frozen, fingerprint


def test_manifest_commit_after_accepted_source_is_allowed(release_history):
    root, _, frozen, fingerprint = release_history
    assert gate.verify_promotion_record(root, frozen) == fingerprint


def test_unaccepted_scanner_edit_fails_even_when_fingerprint_is_unchanged(release_history):
    root, scanner, _, _ = release_history
    scanner.write_text('VERSION = "not accepted"\n')
    changed = commit(root, "C: unreviewed scanner change")
    with pytest.raises(gate.PromotionRecordError, match="accepted_source_tree_drift"):
        gate.verify_promotion_record(root, changed)


def test_docs_only_followup_is_allowed(release_history):
    root, _, frozen, fingerprint = release_history
    (root / "docs/incident-notes.md").write_text("# Synthetic followup\n")
    followup = commit(root, "C: docs only")
    assert frozen != followup
    assert gate.verify_promotion_record(root, followup) == fingerprint


def test_reverted_executable_edit_is_not_false_positive(release_history):
    root, scanner, _, fingerprint = release_history
    scanner.write_text('VERSION = "temporary"\n')
    commit(root, "C: temporary edit")
    scanner.write_text('VERSION = "accepted"\n')
    reverted = commit(root, "D: restore accepted executable bytes")
    assert gate.verify_promotion_record(root, reverted) == fingerprint


def test_workflow_change_is_not_treated_as_documentation(release_history):
    root, _, _, _ = release_history
    workflow = root / ".github/workflows/release.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: changed\n")
    head = commit(root, "C: changed release workflow")
    with pytest.raises(gate.PromotionRecordError, match="accepted_source_tree_drift"):
        gate.verify_promotion_record(root, head)


def test_docs_python_file_is_not_allowed_under_docs_exemption(release_history):
    root, _, _, _ = release_history
    (root / "docs/script.py").write_text("print('changed')\n")
    head = commit(root, "C: executable-shaped docs addition")
    with pytest.raises(gate.PromotionRecordError, match="accepted_source_tree_drift"):
        gate.verify_promotion_record(root, head)


def test_corrupted_release_metadata_still_fails(release_history):
    root, _, _, _ = release_history
    record_path = root / "data/beta-crawler-revision.json"
    record = json.loads(record_path.read_text())
    record["fingerprint"] = "0" * 16
    record_path.write_text(json.dumps(record))
    changed = commit(root, "C: broken fingerprint")
    with pytest.raises(gate.PromotionRecordError, match="release_fingerprint_inconsistent"):
        gate.verify_promotion_record(root, changed)


def test_existing_candidate_without_acceptance_stays_closed(release_history):
    root, _, _, _ = release_history
    record_path = root / "data/beta-crawler-revision.json"
    record = json.loads(record_path.read_text())
    record["status"] = "candidate"
    record_path.write_text(json.dumps(record))
    changed = commit(root, "C: candidate only")
    with pytest.raises(gate.PromotionRecordError, match="release_not_accepted_candidate"):
        gate.verify_promotion_record(root, changed)
