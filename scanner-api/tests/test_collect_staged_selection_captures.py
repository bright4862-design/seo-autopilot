"""Offline checks for receipt-bound, private selection capture."""

import gzip
import hashlib
import json
import stat
from datetime import datetime, timedelta, timezone

import pytest

from scripts import collect_staged_scan_receipts as receipts
from scripts import collect_staged_selection_captures as capture
from tests.test_collect_staged_scan_receipts import Reader, simulated_canary


def timestamp(moment):
    return moment.isoformat(timespec="milliseconds")


def write(path, value):
    content = json.dumps(value).encode()
    path.write_bytes(content)
    path.chmod(0o600)
    return hashlib.sha256(content).hexdigest()


def summarize(report, digest, fresh):
    provenance = report["provenance"]
    return {
        "schema_version": receipts.EVIDENCE_VERSION,
        "production_freeze": False,
        "canary_report_sha256": digest,
        "scan_id": report["scan_id"],
        "attempt_count": report["attempt_count"],
        "source_sha": report["source_sha"],
        "release_fingerprint": report["release_fingerprint"],
        "worker_revision": provenance["worker_revision"],
        "workspace_bucket": receipts.BUCKET,
        "prerequisite_sha256": provenance["prerequisite_sha256"],
        "terminal_status": report["terminal_status"],
        **fresh,
    }


class PlanReader(Reader):
    def __init__(self, workspace):
        super().__init__(workspace)
        self.pins = []
        self.change_after_download = False

    async def read_pinned_plan(self, key, generation):
        self.pins.append((key, generation))
        current = await self.workspace.read(key)
        assert str(current.generation) == generation
        if self.change_after_download:
            await self.workspace.write(key, current.value, generation=current.generation)
        return current.value


async def staged_attempt(monkeypatch, *, limited=False):
    harness, report, _, _ = await simulated_canary(monkeypatch, limited=limited)
    target = harness.scan["website_url"]
    report.update(project_id=harness.scan["project_id"], target_url=target,
                  outcome="limited_throttled" if limited else "complete",
                  functional_500_verified=False)
    site = {
        "site_id": "site-a", "owner_user_id": report["expected_owner_user_id"],
        "project_id": report["project_id"], "request_id": report["request_id"], "target_url": target,
    }
    reader = PlanReader(harness.store)
    canary = receipts.canary_identity(report)
    evidence = await receipts.collect(canary, reader)
    plan_key = harness.prefix + "plan.json"
    raw, generation = harness.store.objects[plan_key]
    plan = json.loads(gzip.decompress(raw))
    plan["job"]["private_field"] = "private-job-fixture"
    plan["state"] = {
        "checkpoint_version": "scan_state_v1_wall_clock", "scan_mode": "standard_500",
        "job_mode": True, "max_pages": 500, "start_url": target,
        "selection_preferred_market": "/en",
        "selection_captured_at": report["scan_started_at"] if limited else report["scan_completed_at"],
        "scan_started_wall_clock": report["scan_started_at"],
        "sitemap_urls": [] if limited else ["/pricing", target + "catalog", target],
        "homepage_links": [] if limited else [target + "catalog", target + "legal?locale=en"],
        "sitemap_diagnostics": {} if limited else {
            "inventory_capped": True, "sitemap_lastmod": {"/pricing": "2026-02-01", target: "private-metadata-fixture"},
            "private_routes": ["private-diagnostics-fixture"],
        },
        "pages": [{"private_body": "private-state-fixture"}],
    }
    # The memory fixture stands in for the producer body stored at that exact
    # generation. Use the real receipt verifier and an in-memory generation pin.
    harness.store.objects[plan_key] = (gzip.compress(json.dumps(plan).encode()), generation)
    return capture.JournalAttempt(site, report, evidence, canary), reader, plan_key, generation


@pytest.mark.asyncio
@pytest.mark.parametrize("limited", [False, True])
async def test_captures_only_exact_selector_fields_and_preserves_order(monkeypatch, limited):
    attempt, reader, key, generation = await staged_attempt(monkeypatch, limited=limited)
    output = await capture.capture_attempt(attempt, reader)
    assert reader.pins == [(key, str(generation))]
    assert output["terminal_anchor"] == {
        "scan_id": attempt.canary.scan_id, "attempt_count": attempt.canary.attempt,
        "frontier_generation": attempt.evidence["frontier_generation"],
        "receipt_snapshot_sha256": attempt.evidence["receipt_snapshot_sha256"],
    }
    assert output["preferred_market"] == "/en"
    assert output["inventory_capped"] is not limited
    assert output["sitemap_urls"] == ([] if limited else ["/pricing", "https://example.com/catalog", "https://example.com/"])
    assert output["homepage_links"] == ([] if limited else ["https://example.com/catalog", "https://example.com/legal?locale=en"])
    assert output["sitemap_lastmod"] == ({} if limited else {"/pricing": "2026-02-01"})
    assert "private-" not in json.dumps(output)


@pytest.mark.asyncio
@pytest.mark.parametrize("drift", ["receipt", "generation", "legacy", "sensitive"])
async def test_rejects_receipt_drift_changed_plan_and_unknown_or_sensitive_inputs(monkeypatch, drift):
    attempt, reader, key, generation = await staged_attempt(monkeypatch)
    if drift == "receipt":
        attempt.evidence["receipt_snapshot_sha256"] = "0" * 64
        error = "corpus_receipt_snapshot_changed"
    elif drift == "generation":
        reader.change_after_download = True
        error = "workspace_changed_during_capture"
    else:
        current = await reader.workspace.read(key)
        if drift == "legacy":
            current.value["state"]["selection_captured_at"] = ""
            error = "plan_exact_selector_inputs_missing"
        else:
            current.value["state"]["sitemap_urls"] = ["/path?access_token=synthetic"]
            current.value["state"]["sitemap_diagnostics"]["sitemap_lastmod"] = {}
            error = "capture_url_sensitive"
        reader.workspace.objects[key] = (gzip.compress(json.dumps(current.value).encode()), generation)
    with pytest.raises(capture.EvidenceError, match=error):
        await capture.capture_attempt(attempt, reader)
    if drift == "receipt":
        assert reader.pins == []


def test_download_requires_observed_generation_before_fetch():
    class Blob:
        generation = 17
        body = gzip.compress(b'{"state":{}}')
        size = len(body)
        downloads = []

        def reload(self, **kwargs):
            assert kwargs == {"timeout": receipts.READ_TIMEOUT_SECONDS, "retry": None}

        def download_as_bytes(self, **kwargs):
            self.downloads.append(kwargs)
            return self.body

    blob = Blob()

    class Bucket:
        def blob(self, key):
            assert key == "scans/scan_key/a1/plan.json"
            return blob

    reader = capture.CaptureStorage(Bucket())
    assert reader._read_pinned_plan("scans/scan_key/a1/plan.json", "17") == {"state": {}}
    assert blob.downloads == [{"if_generation_match": 17, "raw_download": True,
                               "timeout": receipts.READ_TIMEOUT_SECONDS, "retry": None}]
    with pytest.raises(capture.EvidenceError, match="plan_generation_changed"):
        reader._read_pinned_plan("scans/scan_key/a1/plan.json", "16")
    assert len(blob.downloads) == 1


@pytest.mark.asyncio
async def test_full_journal_binds_manifest_and_terminal_reports(tmp_path, monkeypatch):
    _, base, _, _ = await simulated_canary(monkeypatch)
    moment = datetime.now(timezone.utc) - timedelta(hours=1)
    sites = []
    markers = sorted(capture.REFERENCES)
    classes = sorted(capture.SITE_CLASSES)
    for index in range(50):
        sites.append({
            "site_id": f"site-{index}", "request_id": f"request-{index:03d}",
            "project_id": f"project-{index}", "owner_user_id": base["expected_owner_user_id"],
            "target_url": f"https://site-{index}.example/",
            "site_class": classes[index % len(classes)],
            "reference_marker": markers[index] if index < len(markers) else None,
            "expectation": "throttled_limited" if index == 49 else "complete_below_cap",
        })
    manifest = tmp_path / "manifest.json"
    journal = tmp_path / "journal"
    journal.mkdir(mode=0o700)
    manifest_sha = write(manifest, {
        "schema_version": "staged_scan_corpus_v1", "source_sha": base["source_sha"],
        "release_fingerprint": base["release_fingerprint"], "reviewed_by": "fixture-reviewer",
        "reviewed_at": timestamp(moment - timedelta(hours=1)),
        "expires_at": timestamp(moment + timedelta(minutes=30)), "sites": sites,
    })
    write(journal / "manifest.sha256.json", {"manifest_sha256": manifest_sha})
    for index, site in enumerate(sites):
        report = {
            **base, "scan_id": f"scan-{index:03d}", "target_url": site["target_url"],
            "request_id": site["request_id"], "project_id": site["project_id"],
            "observed_at": timestamp(moment), "scan_started_at": timestamp(moment + timedelta(seconds=1)),
            "scan_completed_at": timestamp(moment + timedelta(seconds=3)),
            "terminal_status": "limited" if index == 49 else "complete",
            "outcome": "limited_throttled" if index == 49 else "complete",
            "functional_500_verified": False,
            "selection_coverage": {"pages_checked": 120, "inventory_capped": False,
                                   "inventory_urls": 140, "sections_sha256": "e" * 64},
        }
        common = {key: site[key] for key in ("site_id", "request_id")}
        common["manifest_sha256"] = manifest_sha
        started = {"observed_at": timestamp(moment), "prerequisite_sha256": base["provenance"]["prerequisite_sha256"]}
        write(journal / (site["site_id"] + ".started.json"), {**common, **started})
        report_sha = write(journal / (site["site_id"] + ".report.json"), report)
        receipt_sha = write(journal / (site["site_id"] + ".receipt.json"), summarize(report, report_sha, {
            "worker_runtime_verified": True, "receipt_evidence_verified": True, "unverified": [],
            "frontier_generation": "123", "receipt_snapshot_sha256": "a" * 64,
        }))
        write(journal / (site["site_id"] + ".finished.json"), {
            **common, "observed_at": timestamp(moment + timedelta(seconds=10)), "exit_code": 0, "exit_signal": None,
            "report_sha256": report_sha, "receipt_sha256": None if index == 49 else receipt_sha,
        })

    digest, attempts, inputs = capture.load_journal(manifest, journal)
    assert digest == manifest_sha and len(attempts) == 50 and len(inputs) == 202
    first = journal / "site-0.report.json"
    original = first.read_bytes()
    first.write_bytes(original + b" ")
    with pytest.raises(capture.EvidenceError, match="corpus_journal_evidence_changed"):
        capture.load_journal(manifest, journal)
    first.write_bytes(original)
    first.chmod(0o644)
    with pytest.raises(capture.EvidenceError, match="local_evidence_path_invalid"):
        capture.load_journal(manifest, journal)


def test_output_is_private_exclusive_and_leaves_no_temporary_artifact(tmp_path):
    output = tmp_path / "private.json"
    capture.publish_private(output, {"sites": []})
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert json.loads(output.read_bytes()) == {"sites": []}
    with pytest.raises(FileExistsError):
        capture.publish_private(output, {"changed": True})
    assert json.loads(output.read_bytes()) == {"sites": []}
    assert list(tmp_path.iterdir()) == [output]
