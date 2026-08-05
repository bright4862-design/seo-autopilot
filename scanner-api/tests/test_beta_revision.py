import json
from pathlib import Path

from app.beta_revision import (
    SCANNER_BUILD_REVISION,
    build_revision_record,
    collect_component_versions,
    diff_versions,
    fingerprint,
    live_revision,
    load_recorded_revision,
)
from app.crawler_acceptance import summarize_beta_acceptance

REPO_ROOT = Path(__file__).resolve().parents[2]
BETA_MANIFEST = REPO_ROOT / "data" / "beta-acceptance-manifest.jsonl"


def test_recorded_revision_matches_live_code():
    """Drift gate: the committed freeze must match the running version constants.

    If a version constant is bumped without re-recording the freeze, this fails
    and points at the drifted component.
    """
    recorded = load_recorded_revision()
    drift = diff_versions(recorded, live_revision())
    assert drift == {}, f"beta revision drift; re-run freeze_beta_revision.py: {drift}"
    assert recorded["fingerprint"] == fingerprint(recorded["component_versions"])


def test_live_revision_shape():
    revision = live_revision()
    assert revision["schema_version"] == "beta_crawler_revision_v1"
    assert revision["fingerprint"] == fingerprint(revision["component_versions"])
    # Every component version must be a non-empty string.
    for key, value in revision["component_versions"].items():
        assert isinstance(value, str) and value, key
    assert revision["component_versions"]["scanner_build_revision"] == SCANNER_BUILD_REVISION


def test_fingerprint_is_order_independent():
    components = collect_component_versions()
    reversed_components = dict(reversed(list(components.items())))
    assert fingerprint(components) == fingerprint(reversed_components)


def test_diff_versions_detects_change():
    recorded = build_revision_record(git_commit="abc")
    live = build_revision_record(git_commit="def")
    live["component_versions"]["scanner_version"] = "changed"
    drift = diff_versions(recorded, live)
    assert "scanner_version" in drift
    assert drift["scanner_version"]["live"] == "changed"


def test_scanner_build_revision_participates_in_frozen_fingerprint():
    recorded = build_revision_record()
    live = build_revision_record()
    live["component_versions"]["scanner_build_revision"] = "unknown_build"

    drift = diff_versions(recorded, live)

    assert fingerprint(recorded["component_versions"]) != fingerprint(live["component_versions"])
    assert drift["scanner_build_revision"] == {
        "recorded": SCANNER_BUILD_REVISION,
        "live": "unknown_build",
    }


def test_beta_acceptance_manifest_wellformed():
    lines = [line for line in BETA_MANIFEST.read_text(encoding="utf-8").splitlines() if line.strip()]
    records = [json.loads(line) for line in lines]
    sites = {record["site"] for record in records}
    assert {"shopify", "signal", "basecamp"} <= sites
    for record in records:
        assert record["url"].startswith("https://")
        assert record["scan_mode"] in {"basic", "quick", "deep", "advanced"}
    assert len(sites) == len(records), "manifest site names must be unique"


def _record(site: str, *, passed: bool, error_codes=None, rules=None) -> dict:
    return {
        "site": site,
        "validation": {"passed": passed, "error_codes": error_codes or [], "warning_codes": []},
        "finding_rules": {rule: 1 for rule in (rules or [])},
    }


def test_summarize_beta_acceptance_passes_when_all_pass():
    records = [_record("shopify", passed=True), _record("signal", passed=True)]
    summary = summarize_beta_acceptance(records, [])
    assert summary["acceptance_passed"] is True
    assert summary["freeze_recommendation"] == "freeze_beta_crawler"
    assert summary["contract_passed_sites"] == 2


def test_summarize_beta_acceptance_fails_on_contract_violation():
    records = [
        _record("shopify", passed=False, error_codes=["redirect_marked_indexable"]),
        _record("signal", passed=True),
    ]
    summary = summarize_beta_acceptance(records, [])
    assert summary["acceptance_passed"] is False
    assert summary["freeze_recommendation"] == "patch_or_rerun"


def test_summarize_beta_acceptance_fails_on_scan_failure():
    summary = summarize_beta_acceptance([_record("shopify", passed=True)], [{"site": "signal", "error": "timeout"}])
    assert summary["acceptance_passed"] is False
    assert summary["failed_sites"] == 1


def test_summarize_beta_acceptance_flags_recurring_violation():
    records = [
        _record("shopify", passed=False, error_codes=["soft_404_metadata_noise"]),
        _record("signal", passed=False, error_codes=["soft_404_metadata_noise"]),
    ]
    summary = summarize_beta_acceptance(records, [])
    assert summary["recurring_contract_violations"]["soft_404_metadata_noise"] == ["shopify", "signal"]
