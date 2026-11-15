"""Exercise the real extracted engine through a durable ten-batch chain."""
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree

import pytest

from app import scanner
from app import scan_job
from app.main import apply_post_crawl_transforms
from app.scan_limits import scan_page_limit
from app.staged_scan import StageDependencies, StagedScanRuntime
from app.workspace import MemoryWorkspace
from scripts.export_staged_500_fixture import export_fixture
from tests import fixtures as fx


EXPORTER = Path(__file__).resolve().parents[1] / "scripts" / "export_staged_500_fixture.py"


@pytest.mark.asyncio
async def test_rate_limited_stage_finalizes_saved_evidence_without_more_requests(mock_network, monkeypatch):
    origin = "https://staged-throttle.example"
    page_urls = [f"{origin}/products/{index}" for index in range(60)]
    routes = {
        f"{origin}/robots.txt": {"body": "User-agent: *\nAllow: /", "content_type": "text/plain"},
        f"{origin}/sitemap.xml": fx._xml(fx._sitemap(page_urls)),
        f"{origin}/": fx._html(fx._page("Home")),
        f"{origin}/late-canonical": fx._html(fx._page("Canonical target")),
    }
    for index, url in enumerate(page_urls):
        canonical = f"{origin}/late-canonical" if index % 2 else f"{origin}/"
        routes[url] = fx._html(fx._page("Shop page", h1="", canonical=canonical, links=[f"{origin}/late-link"]))
    requests = mock_network(routes)
    key = "integration-test-key"
    monkeypatch.setenv("SCAN_EVIDENCE_SIGNING_KEY", key)
    scan = {"id": "scan_throttled", "owner_user_id": "owner_150", "project_id": "project_150",
            "request_id": "request_throttled", "attempt_count": 1, "scan_mode": "standard_150",
            "page_cap": 150, "pipeline_mode": "staged", "website_url": origin + "/",
            "respect_robots_txt": True, "owner_attested_robots_override": False, "status": "queued"}
    job = {**scan, "scan_id": scan["id"]}
    limited_writes = []

    async def read(client, scan_id):
        assert scan_id == scan["id"]
        return dict(scan)

    async def start(client, current):
        scan.update(status="crawling", started_at=datetime.now(timezone.utc).isoformat())

    async def progress(client, current, crawled, planned, batch=None):
        scan.update(pages_crawled=crawled, pages_planned=planned, last_committed_batch=batch)

    async def invoke(client, name, envelope):
        assert name == "persistLimitedScanResultV9"
        assert envelope["proof"] == scan_job.create_authority_seal(
            {key: value for key, value in envelope.items() if key != "proof"}, key)
        assert "staged_rate_limit" in envelope["review"]["coverage_reasons"]
        limited_writes.append(envelope)
        scan["status"] = "limited"
        return {"status_code": 200, "body": {"success": True, "fixListId": "limited-list",
            "resultIntegrityVerified": True}}

    async def fail(*args, **kwargs):
        pytest.fail(f"The staged scan failed instead of saving a limited result: {args[2]}")

    class Dispatcher:
        async def enqueue(self, current_job, stage, batch, *, limited=False, not_before=None):
            return None

    monkeypatch.setattr(scan_job, "read_scan_run", read)
    monkeypatch.setattr(scan_job, "invoke_function", invoke)
    store = MemoryWorkspace()
    runtime = StagedScanRuntime(store, Dispatcher(), StageDependencies(
        read, start, progress, scan_job.complete_authority, apply_post_crawl_transforms, fail,
        scanner.ScanState, scanner.plan_scan, scanner.crawl_batch, scanner.finalize_scan,
    ))
    with scan_page_limit(150), scan_job.worker_function_generation("V9"):
        assert (await runtime.process(None, "plan", job))["stage"] == "batch"
        assert (await runtime.process(None, "batch", job, batch=0))["pages_crawled"] == 50
        for url in page_urls:
            routes[url] = {"status": 429, "body": "Please slow down", "headers": {"Retry-After": "3600"}}
        tail = await runtime.process(None, "batch", job, batch=1)
        assert tail["stage"] == "finalize" and tail["batch"] == 2
        requests_before_finalize = len(requests)
        assert (await runtime.process(None, "finalize", job, batch=2, limited=True))["success"] is True
    assert [request.url.path for request in requests[requests_before_finalize:]] == []
    result = (await store.read(runtime._prefix(job) + "result.json.gz")).value
    assert result["pipeline_limit_reason"] == "rate_limit"
    assert result["coverage_probe_evidence"]["stage2_orchestration_state"] == "not_verified"
    assert result["coverage_probe_evidence"]["stage2_orchestration_reason"] == "crawl_rate_limited"
    assert any(row["purpose"] == "internal_link" and row["state"] == "not_verified"
               and row["reason"] == "crawl_rate_limited" for row in result["coverage_probe_evidence"]["observations"])
    assert result["canonical_target_evidence"]["targets_fetched"] == 0
    canonicals = {page["canonical_target_url"]: page for page in result["pages"] if page.get("canonical_target_url")}
    assert canonicals[f"{origin}/"]["canonical_target_evidence_source"] == "crawl"
    assert canonicals[f"{origin}/late-canonical"]["canonical_target_checked"] is False
    assert canonicals[f"{origin}/late-canonical"]["canonical_target_evidence_source"] == "rate_limit"
    assert result["findings"]
    assert scan["status"] == "limited" and len(limited_writes) == 1


def test_exporter_writes_deterministic_static_site_and_refuses_replacement(tmp_path):
    origin = "https://staged-engine.example"
    first, second = tmp_path / "first", tmp_path / "second"

    def export(destination, supplied_origin=origin):
        return subprocess.run([sys.executable, EXPORTER, "--origin", supplied_origin, "--output", destination],
                              cwd=tmp_path, capture_output=True, text=True, timeout=10)

    for destination, supplied_origin in ((first, origin), (second, f"{origin}/")):
        result = export(destination, supplied_origin)
        assert result.returncode == 0, result.stderr
    tree = ElementTree.parse(first / "sitemap.xml")
    urls = [loc.text for loc in tree.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
    assert len(urls) == len(set(urls)) == 640
    assert (first / "robots.txt").read_text() == f"User-agent: *\nAllow: /\nSitemap: {origin}/sitemap.xml\n"
    assert Counter(urlsplit(url).path.split("/")[1] for url in urls) == {
        "solutions": 160, "products": 160, "stores": 160, "insights": 160,
    }
    for url in urls:
        parsed = urlsplit(url)
        assert (parsed.scheme, parsed.netloc) == ("https", "staged-engine.example")
        page_path = parsed.path.removeprefix("/")
        page = (first / page_path).read_text()
        assert f'<link rel="canonical" href="{url}">' in page
        assert page == (second / page_path).read_text()
    files = {item.relative_to(first): item.read_bytes() for item in first.rglob("*") if item.is_file()}
    assert len(files) == 643
    assert files == {item.relative_to(second): item.read_bytes() for item in second.rglob("*") if item.is_file()}
    assert export(first).returncode == 2
    assert files == {item.relative_to(first): item.read_bytes() for item in first.rglob("*") if item.is_file()}
    invalid = tmp_path / "invalid"
    assert export(invalid, origin + "/not-an-origin").returncode == 2
    assert not invalid.exists()
    alias = tmp_path / "alias"
    alias.symlink_to(tmp_path, target_is_directory=True)
    assert export(alias / "invalid").returncode == 2
    assert export(Path("invalid")).returncode == 2
    assert not invalid.exists()


@pytest.mark.asyncio
async def test_500_page_scan_commits_ten_batches_and_duplicate_finalization_is_inert(mock_network, monkeypatch, tmp_path):
    origin = "https://staged-engine.example"
    exported_site = tmp_path / "site"
    export_fixture(origin, exported_site)
    content_types = {".html": "text/html", ".txt": "text/plain", ".xml": "application/xml"}
    routes = {}
    for file in exported_site.rglob("*"):
        if file.is_file():
            relative = file.relative_to(exported_site).as_posix()
            url_path = "" if relative == "index.html" else relative
            routes[f"{origin}/{url_path}"] = {"body": file.read_text(), "content_type": content_types[file.suffix]}
    mock_network(routes)
    monkeypatch.setenv("SCAN_EVIDENCE_SIGNING_KEY", "integration-test-key")
    scan = {"id": "scan_500", "owner_user_id": "owner_500", "project_id": "project_500",
            "request_id": "request_500", "idempotency_key": "request_500", "attempt_count": 1,
            "scan_mode": "standard_500", "page_cap": 500, "pipeline_mode": "staged",
            "website_url": origin + "/", "respect_robots_txt": True,
            "owner_attested_robots_override": False, "status": "queued"}
    job = {**scan, "scan_id": scan["id"]}
    pending, completions, progress_values = [], [], []

    async def read(client, scan_id):
        assert scan_id == scan["id"]
        return dict(scan)

    async def start(client, current):
        scan["status"] = "crawling"
        scan["started_at"] = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        return dict(scan)

    async def progress(client, current, crawled, planned, batch=None):
        assert 0 <= crawled <= planned <= 500
        progress_values.append(crawled)
        return await scan_job.mark_scan_progress(client, current, crawled, planned, batch)

    async def invoke(client, name, envelope, **kwargs):
        assert name == "durableScanWorkerControlV9"
        assert envelope["proof"] == scan_job.create_authority_seal(
            {key: value for key, value in envelope.items() if key != "proof"}, "integration-test-key")
        return {"status_code": 200, "body": {"success": True, "scanRun": dict(scan)}}

    monkeypatch.setattr(scan_job, "invoke_function", invoke)

    async def complete(client, current, result, key):
        assert result["pages_crawled"] == len(result["pages"]) == 500
        assert len({page["url"] for page in result["pages"]}) == 500
        assert result["page_cap"] == 500
        assert result["pipeline_limited"] is False
        completions.append(result)
        scan["status"] = "complete"
        return {"ok": True, "fix_list_id": "list_500"}

    async def fail(*args, **kwargs):
        pytest.fail("The 500-page staged scan failed")

    class Dispatcher:
        async def enqueue(self, current_job, stage, batch, *, limited=False):
            pending.append((stage, current_job, batch, limited))

    store = MemoryWorkspace()
    runtime = StagedScanRuntime(store, Dispatcher(), StageDependencies(
        read, start, progress, complete, apply_post_crawl_transforms, fail,
        scanner.ScanState, scanner.plan_scan, scanner.crawl_batch, scanner.finalize_scan,
    ))
    with scan_page_limit(500):
        await runtime.process(None, "plan", job)
        delivered = []
        while pending:
            stage, task_job, batch, limited = pending.pop(0)
            delivered.append(stage)
            await runtime.process(None, stage, task_job, batch=batch, limited=limited)
        assert delivered.count("batch") == 10
        assert delivered.count("finalize") == 1
        assert progress_values[-1] == 500
        duplicate = await runtime.process(None, "finalize", job, batch=10)
    assert duplicate["skipped"] == "already_terminal"
    assert len(completions) == 1
    # Exercise the real review and the actual V9 persistence/reader seal seam,
    # rather than stopping at a successful crawl or a stubbed completion call.
    result = completions[0]
    (tmp_path / "scan-500.json").write_text(json.dumps(result))
    review = scan_job.run_local_review_isolated(result)
    original_envelope = scan_job.build_completion_envelope(scan, result, review, "integration-test-key")
    with scan_job.worker_function_generation("V9"):
        envelope = scan_job.build_completion_envelope(scan, result, review, "integration-test-key")
    assert len(json.dumps(envelope)) < len(json.dumps(original_envelope))
    assert envelope["scan"]["result_ready_at"] == result["result_ready_at"]
    (tmp_path / "completion-500.json").write_text(json.dumps(envelope))
    script = """
      import assert from 'node:assert/strict';
      import {readFileSync} from 'node:fs';
      import {webcrypto} from 'node:crypto';
      import {buildAuthoritySnapshot, firstFailedAuthorityPredicate} from './base44/functions/persistDurableScanAuthorityV9/authoritySnapshot.js';
      import {stagedCompletionTime} from './base44/functions/persistDurableScanAuthorityV9/completionTimestamp.js';
      import {authorityRowsFromSnapshot} from './base44/functions/persistDurableScanAuthorityV9/authorityRows.js';
      import {authoritySnapshotFromRows, createAuthoritySeal, verifyAuthoritySeal} from './base44/functions/getCustomerScanResultV9/projection.js';
      const {body, original, scan} = JSON.parse(readFileSync(0, 'utf8'));
      const finishedAt = stagedCompletionTime(scan, body.scan);
      assert.ok(Date.parse(finishedAt) > Date.parse(scan.started_at));
      const options = {scan:body.scan,review:body.review,identity:body.identity,userId:body.identity.owner_user_id,now:finishedAt,identityVersion:'evidence_url_identity_v2_published_route'};
      assert.equal(firstFailedAuthorityPredicate(body.scan,body.review,{identityVersion:options.identityVersion}),'');
      const snapshot = buildAuthoritySnapshot(options);
      assert.deepEqual(snapshot,buildAuthoritySnapshot({...options,scan:original.scan,review:original.review}));
      const rows = authorityRowsFromSnapshot(snapshot,{fixListId:'list_500',ownerUserId:options.userId});
      const restored = authoritySnapshotFromRows({run:{...rows.scanRun,id:body.identity.scan_id,project_id:body.identity.project_id},fixList:{...rows.fixList,id:'list_500'},fixItems:rows.fixItems,userId:options.userId});
      assert.deepEqual(restored,snapshot);
      assert.equal(restored.scan.completed_at, finishedAt);
      assert.equal(restored.sealed_at, finishedAt);
      const proof = await createAuthoritySeal(snapshot,'integration-test-key',webcrypto);
      assert.equal(await verifyAuthoritySeal(restored,'integration-test-key',proof,webcrypto),true);
      assert.equal(snapshot.scan.pages_crawled,500);
      assert.equal(snapshot.scan.page_cap,500);
    """
    checked = subprocess.run(["node", "--input-type=module", "-e", script],
                             input=json.dumps({"body": envelope, "original": original_envelope, "scan": scan}), text=True, capture_output=True,
                             cwd=Path(__file__).resolve().parents[2], timeout=30)
    assert checked.returncode == 0, checked.stderr
