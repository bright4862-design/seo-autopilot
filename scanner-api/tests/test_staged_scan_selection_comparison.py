import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "scanner-api/scripts/compare_staged_scan_selection.py"
BASELINE = "689a7fb43825f322af70188e7426730552daebd9"
CANDIDATE = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
requires_git_history = pytest.mark.skipif(
    subprocess.run(["git", "merge-base", "--is-ancestor", BASELINE, CANDIDATE], cwd=ROOT, capture_output=True).returncode != 0,
    reason="exact historical selector replay requires a full local Git checkout",
)
REFERENCES = {
    "funbooker": "funbooker.com",
    "pretto": "pretto.fr",
    "center_street_lending": "centerstreetlending.com",
    "norris_wines": "norriswines.com",
}


def sha256(value):
    return hashlib.sha256(value).hexdigest()


@pytest.fixture
def comparison_files(tmp_path):
    def create(*, change=None, single_section=False):
        fingerprint = json.loads(subprocess.check_output([
            "git", "show", f"{CANDIDATE}:data/beta-crawler-revision.json",
        ], cwd=ROOT))["fingerprint"]
        manifest = {
            "schema_version": "staged_scan_corpus_v1",
            "source_sha": CANDIDATE,
            "release_fingerprint": fingerprint,
            "sites": [],
        }
        captures = {"schema_version": "staged_scan_selection_captures_v1", "sites": []}
        for index in range(50):
            marker = list(REFERENCES)[index] if index < len(REFERENCES) else None
            host = REFERENCES.get(marker, f"synthetic-site-{index}.example")
            target = f"https://{host}/"
            site_id = f"site_{index}"
            manifest["sites"].append({"site_id": site_id, "target_url": target, "reference_marker": marker})
            # An ordered inventory can favor the early route families under v7.
            sitemap = [f"{target}shop/{section}/page-{leaf}" for section in range(80) for leaf in range(2)]
            if single_section or marker:
                sitemap = [f"{target}supplied-private-section/page-{leaf}" for leaf in range(170)]
            captures["sites"].append({
                "site_id": site_id,
                "start_url": target,
                "captured_at": "2026-11-11T12:00:00Z",
                "sitemap_urls": sitemap,
                "homepage_links": sitemap[-2:],
                "sitemap_lastmod": {sitemap[0]: "2026-11-01", sitemap[1]: "2024-11-01"},
                "preferred_market": "",
                "inventory_capped": False,
            })
        captures["sites"][0]["terminal_anchor"] = {
            "scan_id": "scan_123", "attempt_count": 2, "frontier_generation": "123456", "receipt_snapshot_sha256": "a" * 64,
        }
        if change:
            change(manifest, captures)
        manifest_file = tmp_path / "manifest.json"
        manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
        captures.setdefault("corpus_manifest_sha256", sha256(manifest_file.read_bytes()))
        captures_file = tmp_path / "captures.json"
        captures_file.write_text(json.dumps(captures), encoding="utf-8")
        return manifest_file, captures_file, tmp_path / "private-comparison.json"

    return create


def compare(manifest, captures, output):
    return subprocess.run([
        sys.executable, str(TOOL), "--manifest", str(manifest), "--captures", str(captures), "--output", str(output),
    ], cwd=ROOT, check=False, capture_output=True, text=True)


@requires_git_history
def test_replay_compares_exact_git_selectors_and_writes_a_private_bound_artifact(comparison_files):
    def relative_sitemap_entry(_manifest, captures):
        captures["sites"][1]["sitemap_urls"].append("/supplied-private-section/relative")

    manifest, captures, output = comparison_files(change=relative_sitemap_entry)
    result = compare(manifest, captures, output)
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_bytes())
    assert report["schema_version"] == "staged_scan_selection_comparison_v1"
    assert report["baseline_source_sha"] == BASELINE
    assert report["baseline_sampling_version"] == "balanced_sitemap_buckets_v7_commercial_hubs_before_repeated_leaves"
    assert report["candidate_source_sha"] == CANDIDATE
    assert report["corpus_manifest_sha256"] == sha256(manifest.read_bytes())
    assert report["captures_sha256"] == sha256(captures.read_bytes())
    assert report["site_count"] == 50
    assert report["selection_comparison_verified"] is True
    assert report["live_terminal_evidence_verified"] is False
    assert report["summary"]["candidate_150_sections_never_selected"] < report["summary"]["v7_150_sections_never_selected"]
    assert {row["reference_marker"] for row in report["summary"]["references"]} == set(REFERENCES)
    assert all(row["lost_v7_sections_at_150"] == 0 for row in report["summary"]["references"])
    first_site = report["sites"][0]
    assert first_site["claimed_terminal_anchor"]["attempt_count"] == 2
    assert first_site["inventory_urls"] == first_site["candidate_selected_urls_500"] == 170
    assert first_site["sections"] == [{
        "section_sha256": sha256(b"/supplied-private-section"), "discovered": 170,
        "v7_selected_150": 149, "candidate_selected_150": 149, "candidate_selected_500": 170,
    }]
    assert report["sites"][1]["inventory_urls"] == 171
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert b"supplied-private-section" not in output.read_bytes()
    assert b"https://" not in output.read_bytes()
    original = output.read_bytes()
    assert compare(manifest, captures, output).returncode != 0
    assert output.read_bytes() == original


@requires_git_history
def test_no_improvement_cannot_pass_from_the_500_page_capacity_alone(comparison_files):
    manifest, captures, output = comparison_files(single_section=True)
    result = compare(manifest, captures, output)
    assert result.returncode == 1, result.stderr
    report = json.loads(output.read_bytes())
    assert report["selection_comparison_verified"] is False
    assert report["summary"]["v7_150_sections_never_selected"] == report["summary"]["candidate_150_sections_never_selected"]
    assert report["sites"][0]["sections"][0]["candidate_selected_500"] > report["sites"][0]["sections"][0]["candidate_selected_150"]


@requires_git_history
def test_a_reference_lost_section_fails_even_as_aggregate_coverage_improves(comparison_files):
    def change(_manifest, captures):
        reference = captures["sites"][0]
        sitemap = [f"{reference['start_url']}shop/{section}/page-{leaf}" for section in range(220) for leaf in range(2)]
        reference.update(sitemap_urls=sitemap, homepage_links=sitemap[-2:], sitemap_lastmod={})

    manifest, captures, output = comparison_files(change=change)
    result = compare(manifest, captures, output)
    assert result.returncode == 1, result.stderr
    report = json.loads(output.read_bytes())
    summary = report["summary"]
    assert summary["candidate_150_sections_never_selected"] < summary["v7_150_sections_never_selected"]
    references = {row["reference_marker"]: row["lost_v7_sections_at_150"] for row in summary["references"]}
    assert references["funbooker"] > 0
    assert report["selection_comparison_verified"] is False


def test_summary_uses_matched_cap_and_rejects_a_reference_section_swap():
    spec = importlib.util.spec_from_file_location("selection_comparison", TOOL)
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    kept = {"v7_selected_150": 1, "candidate_selected_150": 1, "candidate_selected_500": 1}
    added = {"v7_selected_150": 0, "candidate_selected_150": 1, "candidate_selected_500": 1}
    lost = {"v7_selected_150": 1, "candidate_selected_150": 0, "candidate_selected_500": 1}
    ref = {"site_id": "a_reference", "reference_marker": "pretto", "sections": [lost, added]}
    other = {"site_id": "other", "reference_marker": None, "sections": [added]}
    summary, verified = tool.summarize([ref, other])
    assert summary["candidate_150_sections_never_selected"] < summary["v7_150_sections_never_selected"]
    assert summary["references"][0]["lost_v7_sections_at_150"] == 1
    assert verified is False
    ref["sections"] = [kept]
    assert tool.summarize([ref, other])[1] is True


@pytest.mark.parametrize("change, expected", [
    (lambda m, c: c.update(corpus_manifest_sha256="0" * 64), "captures_manifest_mismatch"),
    (lambda m, c: m["sites"][0].update(reference_marker="pretto"), "corpus_reference_host_mismatch"),
    (lambda m, c: c["sites"].pop(), "capture_inventory_mismatch"),
    (lambda m, c: m.update(release_fingerprint="0" * 16), "candidate_fingerprint_mismatch"),
])
def test_unbound_inputs_fail_without_exposing_urls_or_writing_artifacts(comparison_files, change, expected):
    paths = comparison_files(change=change)
    result = compare(*paths)
    assert result.returncode == 2
    assert result.stderr.strip() == expected
    assert not paths[2].exists()
