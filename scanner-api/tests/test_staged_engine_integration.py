"""Exercise the real extracted engine through a durable ten-batch chain."""
import json
from pathlib import Path
import subprocess

import pytest

from app import scanner
from app import scan_job
from app.main import apply_post_crawl_transforms
from app.scan_limits import scan_page_limit
from app.staged_scan import StageDependencies, StagedScanRuntime
from app.workspace import MemoryWorkspace


@pytest.mark.asyncio
async def test_500_page_scan_commits_ten_batches_and_duplicate_finalization_is_inert(mock_network, monkeypatch, tmp_path):
    from tests import fixtures as fx
    origin = "https://staged-engine.example"
    urls = [f"{origin}/{section}/{i}" for section in ("solutions", "products", "stores", "insights") for i in range(160)]
    mock_network({
        origin + "/": fx._html(fx._page("Home")),
        origin + "/robots.txt": {"body": "User-agent: *\nAllow: /", "content_type": "text/plain"},
        origin + "/sitemap.xml": fx._xml(fx._sitemap(urls)),
        **{url: fx._html(fx._page(url)) for url in urls},
    })
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
    (tmp_path / "completion-500.json").write_text(json.dumps(envelope))
    script = """
      import assert from 'node:assert/strict';
      import {readFileSync} from 'node:fs';
      import {webcrypto} from 'node:crypto';
      import {buildAuthoritySnapshot, firstFailedAuthorityPredicate} from './base44/functions/persistDurableScanAuthorityV9/authoritySnapshot.js';
      import {authorityRowsFromSnapshot} from './base44/functions/persistDurableScanAuthorityV9/authorityRows.js';
      import {authoritySnapshotFromRows, createAuthoritySeal, verifyAuthoritySeal} from './base44/functions/getCustomerScanResultV9/projection.js';
      const {body, original} = JSON.parse(readFileSync(0, 'utf8'));
      const options = {scan:body.scan,review:body.review,identity:body.identity,userId:body.identity.owner_user_id,now:'2026-11-11T12:00:00.000Z',identityVersion:'evidence_url_identity_v2_published_route'};
      assert.equal(firstFailedAuthorityPredicate(body.scan,body.review,{identityVersion:options.identityVersion}),'');
      const snapshot = buildAuthoritySnapshot(options);
      assert.deepEqual(snapshot,buildAuthoritySnapshot({...options,scan:original.scan,review:original.review}));
      const rows = authorityRowsFromSnapshot(snapshot,{fixListId:'list_500',ownerUserId:options.userId});
      const restored = authoritySnapshotFromRows({run:{...rows.scanRun,id:body.identity.scan_id,project_id:body.identity.project_id},fixList:{...rows.fixList,id:'list_500'},fixItems:rows.fixItems,userId:options.userId});
      assert.deepEqual(restored,snapshot);
      const proof = await createAuthoritySeal(snapshot,'integration-test-key',webcrypto);
      assert.equal(await verifyAuthoritySeal(restored,'integration-test-key',proof,webcrypto),true);
      assert.equal(snapshot.scan.pages_crawled,500);
      assert.equal(snapshot.scan.page_cap,500);
    """
    checked = subprocess.run(["node", "--input-type=module", "-e", script],
                             input=json.dumps({"body": envelope, "original": original_envelope}), text=True, capture_output=True,
                             cwd=Path(__file__).resolve().parents[2], timeout=30)
    assert checked.returncode == 0, checked.stderr
