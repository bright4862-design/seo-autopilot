import json
from pathlib import Path

import pytest

from app.beta_revision import (
    CROSS_RUNTIME_SCHEMA_VERSION,
    SCANNER_BUILD_REVISION,
    build_revision_record,
    collect_component_versions,
    diff_versions,
    fingerprint,
    live_revision,
    load_cross_runtime_components,
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


# --------------------------------------------------------- cross-runtime --
#
# Base44 functions and the frontend can change release truth, but Python cannot
# import them, so their markers are declared in data and merged here. The
# frontend suite asserts the same participation against the recorded record; it
# cannot run this, because collect_component_versions reaches bs4/httpx and the
# frontend CI job installs Node only.


def test_cross_runtime_components_are_merged_into_the_live_fingerprint():
    declared = load_cross_runtime_components()
    components = collect_component_versions()

    assert declared, "no cross-runtime markers are declared"
    for key, value in declared.items():
        assert components[key] == value, key


def test_every_cross_runtime_component_moves_the_fingerprint():
    """Presence is not participation: each declared marker must be hashed."""
    components = collect_component_versions()
    baseline = fingerprint(components)

    for key in load_cross_runtime_components():
        without = {name: value for name, value in components.items() if name != key}
        assert fingerprint(without) != baseline, f"{key} does not move the fingerprint"


def test_cross_runtime_input_fails_closed_when_missing(tmp_path):
    with pytest.raises(RuntimeError, match="missing"):
        load_cross_runtime_components(tmp_path / "absent.json")


def test_cross_runtime_input_fails_closed_on_malformed_json(tmp_path):
    source = tmp_path / "components.json"
    source.write_text("{not json", encoding="utf-8")
    with pytest.raises(RuntimeError, match="valid JSON"):
        load_cross_runtime_components(source)


def test_cross_runtime_input_fails_closed_on_wrong_schema(tmp_path):
    source = tmp_path / "components.json"
    source.write_text(json.dumps({"schema_version": "v0", "components": {"a": "b"}}), encoding="utf-8")
    with pytest.raises(RuntimeError, match=CROSS_RUNTIME_SCHEMA_VERSION):
        load_cross_runtime_components(source)


@pytest.mark.parametrize(
    "components",
    [{}, {"Not Snake": "value"}, {"empty_value": "   "}, {"wrong_type": 3}],
)
def test_cross_runtime_input_rejects_unusable_component_maps(tmp_path, components):
    source = tmp_path / "components.json"
    source.write_text(
        json.dumps({"schema_version": CROSS_RUNTIME_SCHEMA_VERSION, "components": components}),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError):
        load_cross_runtime_components(source)


def test_cross_runtime_components_do_not_collide_with_python_components():
    """A collision would let one runtime silently redefine another's marker."""
    declared = set(load_cross_runtime_components())
    components = collect_component_versions()
    python_only = set(components) - declared

    assert python_only, "no python-owned components remain"
    assert declared.isdisjoint(python_only)


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
