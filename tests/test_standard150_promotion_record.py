"""Fail-closed Standard-150 promotion metadata, separate from worker staging."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import assert_standard150_promotion_record as gate


@pytest.fixture
def frozen_record(tmp_path, monkeypatch):
    # A successful ancestry result stands in for an accepted ancestor.
    monkeypatch.setattr(gate.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0))
    (tmp_path / "data").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/accepted.md").write_text("Accepted by the release gate\n")
    components = {"scanner_version": "v8", "sampling_version": "v7"}
    fingerprint = hashlib.sha256(
        json.dumps(components, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]
    payload = {
        "status": "frozen_beta",
        "git_commit": "b" * 40,
        "acceptance_report": "docs/accepted.md",
        "component_versions": components,
        "fingerprint": fingerprint,
    }
    def save():
        (tmp_path / "data/beta-crawler-revision.json").write_text(json.dumps(payload))
    save()
    return tmp_path, payload, save


def test_frozen_record_with_accepted_ancestor_passes_source_gate(frozen_record):
    root, record, _ = frozen_record
    assert gate.verify_promotion_record(root, "a" * 40) == record["fingerprint"]


def test_explicit_candidate_is_blocked_even_if_fingerprint_matches(frozen_record):
    root, record, save = frozen_record
    record["status"] = "candidate"
    save()
    with pytest.raises(gate.PromotionRecordError, match="release_not_accepted_candidate"):
        gate.verify_promotion_record(root, "a" * 40)


def test_missing_report_fails_closed(frozen_record):
    root, record, save = frozen_record
    record["acceptance_report"] = ""
    save()
    with pytest.raises(gate.PromotionRecordError, match="acceptance_report_missing"):
        gate.verify_promotion_record(root, "a" * 40)


@pytest.mark.parametrize("report", [
    "../outside.md", "/tmp/report.md", "notes/accepted.md",
    "docs/../../elsewhere.md", "docs/not-markdown.txt",
])
def test_report_must_stay_under_docs(frozen_record, report):
    root, record, save = frozen_record
    record["acceptance_report"] = report
    save()
    with pytest.raises(gate.PromotionRecordError, match="acceptance_report_path_invalid"):
        gate.verify_promotion_record(root, "a" * 40)


def test_absent_report_file_fails_closed(frozen_record):
    root, record, save = frozen_record
    record["acceptance_report"] = "docs/not-present.md"
    save()
    with pytest.raises(gate.PromotionRecordError, match="acceptance_report_unavailable"):
        gate.verify_promotion_record(root, "a" * 40)


def test_changed_component_marker_without_refreeze_fails(frozen_record):
    root, record, save = frozen_record
    record["component_versions"]["sampling_version"] = "unexpected-v9"
    save()
    with pytest.raises(gate.PromotionRecordError, match="release_fingerprint_inconsistent"):
        gate.verify_promotion_record(root, "a" * 40)


def test_unrelated_or_missing_accepted_commit_fails(frozen_record, monkeypatch):
    root, record, _ = frozen_record
    monkeypatch.setattr(gate.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=1))
    with pytest.raises(gate.PromotionRecordError, match="accepted_git_commit_not_ancestor"):
        gate.verify_promotion_record(root, "a" * 40)


def test_invalid_source_sha_fails(frozen_record):
    root, _, _ = frozen_record
    with pytest.raises(gate.PromotionRecordError, match="source_sha_invalid"):
        gate.verify_promotion_record(root, "bad")


@pytest.fixture
def v9_release_history(tmp_path):
    root = tmp_path

    def files(relative, contents):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)

    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()

    def commit():
        git("add", ".")
        git("-c", "user.name=Test", "-c", "user.email=test@example.test", "commit", "-qm", "source")
        return git("rev-parse", "HEAD")

    def routes(generation, route_suffix="1"):
        files(gate.BASE44_ROUTES, json.dumps({"generation": generation}))
        files(gate.GENERATED_V9_ROUTES, json.dumps({"functions": {
            f"{name}V9": {"route_name": f"{name}V9B{route_suffix * 16}"} for name in gate.SCANNER_FUNCTIONS
        }}))

    def accept(source):
        components = {"scanner_version": "v9"}
        files("docs/accepted.md", "Accepted source\n")
        files("data/beta-crawler-revision.json", json.dumps({
            "status": "frozen_beta", "git_commit": source, "acceptance_report": "docs/accepted.md",
            "component_versions": components,
            "fingerprint": hashlib.sha256(json.dumps(components, separators=(",", ":")).encode()).hexdigest()[:16],
        }))

    git("init", "-q")
    routes("v8")
    for generation in ("V8", "V9"):
        for name in gate.SCANNER_FUNCTIONS:
            files(f"base44/functions/{name}{generation}/entry.ts", f"{name}{generation}\n")
    return root, files, commit, routes, accept


def test_first_v9_cutover_accepts_frozen_package_bytes_with_same_alias_history(v9_release_history):
    root, files, commit, routes, accept = v9_release_history
    accepted = commit()
    routes("v9")
    accept(accepted)
    first_cutover = commit()
    assert gate.verify_promotion_record(root, first_cutover, "site-and-functions")
    files("docs/retry.md", "Same aliases\n")
    assert gate.verify_promotion_record(root, commit(), "site-and-functions")


@pytest.mark.parametrize("file", [
    gate.GENERATED_V9_ROUTES,
    "base44/functions/startStandardScanJobV9/entry.ts",
    "base44/functions/getCustomerScanResultV8/entry.ts",
    "base44/shared/environment.ts",
    "base44/functions/stripeWebhook/entry.ts",
])
def test_v9_promotion_rejects_package_drift_even_from_accepted_ancestor(v9_release_history, file):
    root, files, commit, routes, accept = v9_release_history
    accepted = commit()
    routes("v9")
    accept(accepted)
    files(file, "Changed after acceptance\n")
    with pytest.raises(gate.PromotionRecordError, match="active_v9_packages_differ_from_accepted_source"):
        gate.verify_promotion_record(root, commit(), "site-and-functions")


def test_later_public_v9_site_fails_closed_if_historical_aliases_differ(v9_release_history):
    root, _, commit, routes, accept = v9_release_history
    accepted = commit()
    routes("v9")
    accept(accepted)
    assert gate.verify_promotion_record(root, commit(), "site-and-functions")
    routes("v9", "2")
    accept(commit())
    current = commit()
    assert gate.verify_promotion_record(root, current, "scanner-functions")
    with pytest.raises(gate.PromotionRecordError, match="active_v9_site_would_omit_earlier_public_aliases"):
        gate.verify_promotion_record(root, current, "site-and-functions")


def test_restart_recovery_binds_independent_probe_package_to_accepted_source(v9_release_history):
    root, files, commit, routes, accept = v9_release_history
    probe = "base44/functions/fixlistStagedRuntimeControl/entry.ts"
    files(probe, "Original probe\n")
    accepted = commit()
    routes("v9")
    accept(accepted)
    assert gate.verify_promotion_record(root, commit(), "recover-functions")
    files(probe, "Changed after acceptance\n")
    with pytest.raises(gate.PromotionRecordError, match="active_v9_packages_differ_from_accepted_source"):
        gate.verify_promotion_record(root, commit(), "recover-functions")


def test_promotion_guard_scoped_to_new_promotion_not_rollback():
    operator = (ROOT / "scripts/fixlist-cloud-operator.sh").read_text()
    assert 'if [[ "$OPERATION" == "promote-worker" ]]; then' in operator
    assert 'assert_standard150_promotion_record.py" --source-sha "$SOURCE_SHA"' in operator
    assert "rollback-worker)" in operator
    assert "promote_revision()" in operator


def test_all_production_publish_paths_enforce_accepted_release_metadata_first():
    root = ROOT
    targets = [
        ("scripts/deploy-base44-beta-functions.sh", 'fixlist_install_base44_cli "$TMP"'),
        ("scripts/deploy-base44-beta-site.sh", 'fixlist_install_base44_cli "$TMP"'),
    ]
    guard = 'assert_standard150_promotion_record.py" --source-sha "$SOURCE_SHA"'
    for path, mutation in targets:
        source = (root / path).read_text()
        assert guard in source, path
        assert source.index(guard) < source.index(mutation), path

    operator = (root / "scripts/fixlist-cloud-operator.sh").read_text()
    promote = operator.split("promote_revision() {", 1)[1].split("\n}", 1)[0]
    assert guard in promote
    assert promote.index(guard) < promote.index('gcloud run services update-traffic "$CLOUD_RUN_SERVICE"')
    # Existing incidents must still be able to use the explicit rollback path.
    assert 'if [[ "$OPERATION" == "promote-worker" ]]; then' in promote
