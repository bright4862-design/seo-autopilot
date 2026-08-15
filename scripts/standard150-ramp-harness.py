#!/usr/bin/env python3
"""Read-only-observation / customer-submit load harness for Standard 150.

Exercises the *server-owned* beta path only:
  customer token -> startStandardScanJob (NO scan_id supplied)
  -> server-created ScanRun -> getCustomerScanResult polling.

It never creates, updates, or deletes ScanRun/FixList/FixItem records directly.
Targets JSON is an array of {"email", "url", "project_id"}. Tokens JSON maps
email -> bearer token. Use dedicated beta test accounts only.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

APP_ID = "6a498732ec779dfaaeab0e53"
BASE44_API = "https://base44.app"
TERMINAL = {"complete", "limited", "failed", "cancelled"}
GOOD = {"complete", "limited"}


def unwrap(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    data = value.get("data")
    return data if isinstance(data, dict) else value


def auth_headers(token: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token}", "content-type": "application/json"}


async def invoke(client: httpx.AsyncClient, token: str, function: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    response = await client.post(
        f"{BASE44_API}/api/apps/{APP_ID}/functions/{function}",
        headers=auth_headers(token),
        json=payload,
        timeout=60.0,
    )
    try:
        body = unwrap(response.json())
    except Exception:
        body = {}
    return response.status_code, body


@dataclass
class Submission:
    email: str
    url: str
    project_id: str
    request_id: str = field(default_factory=lambda: f"scanreq_ramp_{uuid.uuid4()}")
    scan_id: str = ""
    http_status: int = 0
    accepted: bool = False
    failure_code: str = ""
    run: dict[str, Any] = field(default_factory=dict)
    submitted_at: float = 0.0
    terminal_at: float = 0.0


async def list_runs(client: httpx.AsyncClient, token: str, project_id: str) -> list[dict[str, Any]]:
    status, body = await invoke(client, token, "getCustomerScanResult", {
        "action": "list", "project_id": project_id, "limit": 20,
    })
    if status != 200:
        return []
    rows = body.get("runs")
    return rows if isinstance(rows, list) else []


async def submit(client: httpx.AsyncClient, token: str, item: Submission) -> None:
    item.submitted_at = time.monotonic()
    status, body = await invoke(client, token, "startStandardScanJob", {
        "request_id": item.request_id,
        "idempotency_key": item.request_id,
        "project_id": item.project_id,
        "website_url": item.url,
        "submitted_url": item.url,
        "scan_mode": "standard_150",
    })
    item.http_status = status
    item.accepted = body.get("accepted") is True
    item.failure_code = str(body.get("failure_code") or "")
    item.scan_id = str(body.get("scan_id") or body.get("scan_run_id") or "")


async def poll_one(client: httpx.AsyncClient, token: str, item: Submission) -> None:
    if not item.scan_id:
        return
    status, body = await invoke(client, token, "getCustomerScanResult", {
        "action": "get", "scan_id": item.scan_id,
    })
    if status != 200:
        return
    run = body.get("run")
    if isinstance(run, dict):
        item.run = run
        if str(run.get("status") or "").lower() in TERMINAL and not item.terminal_at:
            item.terminal_at = time.monotonic()


async def wait_terminal(client: httpx.AsyncClient, tokens: dict[str, str], items: list[Submission], timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    pending = [item for item in items if item.accepted and item.scan_id]
    while pending and time.monotonic() < deadline:
        await asyncio.gather(*(poll_one(client, tokens[item.email], item) for item in pending))
        pending = [item for item in pending if not item.terminal_at]
        if pending:
            await asyncio.sleep(5)


def log_quality(scan_ids: list[str], since: datetime, project: str | None) -> dict[str, Any]:
    if not project or not scan_ids:
        return {"available": False, "reason": "gcp project or scan ids not supplied"}
    ids = " OR ".join(f'jsonPayload.scan_id="{scan_id}"' for scan_id in scan_ids)
    stamp = since.isoformat().replace("+00:00", "Z")
    filt = (
        'resource.type="cloud_run_revision" '
        'jsonPayload.event="scan_job_crawl_completed" '
        f'timestamp>="{stamp}" AND ({ids})'
    )
    cmd = ["gcloud", "logging", "read", filt, "--project", project, "--format=json", "--limit=200"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=True).stdout
        rows = json.loads(out or "[]")
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        return {"available": False, "reason": str(exc)[:200]}
    payloads = [row.get("jsonPayload") or {} for row in rows]
    return {
        "available": True,
        "events": len(payloads),
        "rate_limited_pages": sum(int(p.get("rate_limited_pages") or 0) for p in payloads),
        "server_error_pages": sum(int(p.get("server_error_pages") or 0) for p in payloads),
        "failed_pages": sum(int(p.get("failed_pages") or 0) for p in payloads),
        "pages_crawled": sum(int(p.get("pages_crawled") or 0) for p in payloads),
    }


def report(items: list[Submission], logs: dict[str, Any], before: set[str] | None = None, after: set[str] | None = None) -> dict[str, Any]:
    accepted = [i for i in items if i.accepted]
    terminal = [i for i in accepted if str(i.run.get("status") or "").lower() in TERMINAL]
    good = [i for i in terminal if str(i.run.get("status") or "").lower() in GOOD]
    scores = [float(i.run.get("evidence_quality_score") or 0) for i in good]
    failures: list[str] = []
    if len(terminal) != len(accepted):
        failures.append(f"{len(accepted) - len(terminal)} accepted scan(s) did not terminalize")
    for item in good:
        if item.run.get("release_gate_eligible") is not True:
            failures.append(f"{item.scan_id}: release_gate_eligible is not true")
        if len(str(item.run.get("authority_proof") or "")) != 64:
            failures.append(f"{item.scan_id}: missing 64-hex authority proof")
        if not str(item.run.get("fix_list_id") or ""):
            failures.append(f"{item.scan_id}: missing fix_list_id")
    bad_codes = {str(i.run.get("error_code") or "") for i in terminal}
    for code in {"worker_terminal_drain_timeout", "orphaned_no_terminal_state"} & bad_codes:
        failures.append(f"lifecycle failure observed: {code}")
    new_runs = sorted((after or set()) - (before or set())) if before is not None and after is not None else []
    return {
        "submitted": len(items),
        "accepted": len(accepted),
        "terminal": len(terminal),
        "good": len(good),
        "statuses": [str(i.run.get("status") or "") for i in items],
        "failure_codes": [i.failure_code for i in items if i.failure_code],
        "new_scan_runs": new_runs,
        "evidence_quality_min": min(scores) if scores else None,
        "evidence_quality_mean": (sum(scores) / len(scores)) if scores else None,
        "logs": logs,
        "failures": failures,
        "passed": not failures,
    }


async def main_async(args: argparse.Namespace) -> int:
    tokens = json.loads(Path(args.tokens).read_text())
    targets = json.loads(Path(args.targets).read_text())
    if not isinstance(tokens, dict) or not isinstance(targets, list) or not targets:
        raise SystemExit("tokens must be an object and targets must be a non-empty array")
    selected = targets[: max(1, args.count)]
    if args.double_submit:
        selected = [targets[0], targets[0]]
    items = [Submission(email=str(t["email"]), url=str(t["url"]), project_id=str(t["project_id"])) for t in selected]
    for item in items:
        if item.email not in tokens:
            raise SystemExit(f"missing token for {item.email}")
    if args.double_submit:
        items[1].request_id = f"scanreq_ramp_{uuid.uuid4()}"

    started = datetime.now(timezone.utc) - timedelta(seconds=15)
    async with httpx.AsyncClient() as client:
        before = set()
        if args.double_submit:
            before = {str(r.get("id") or r.get("scan_id") or "") for r in await list_runs(client, tokens[items[0].email], items[0].project_id)}
        await asyncio.gather(*(submit(client, tokens[i.email], i) for i in items))
        await wait_terminal(client, tokens, items, args.timeout)
        after = set()
        if args.double_submit:
            after = {str(r.get("id") or r.get("scan_id") or "") for r in await list_runs(client, tokens[items[0].email], items[0].project_id)}

    logs = log_quality([i.scan_id for i in items if i.scan_id], started, args.gcp_project)
    result = report(items, logs, before if args.double_submit else None, after if args.double_submit else None)
    if args.double_submit:
        if len(result["new_scan_runs"]) != 1:
            result["failures"].append(f"same-owner double-submit created {len(result['new_scan_runs'])} new ScanRuns; expected 1")
        if len([i for i in items if i.accepted]) != 1:
            result["failures"].append("same-owner double-submit must accept exactly one request")
        if len([i for i in items if i.failure_code == "scan_admission_busy"]) != 1:
            result["failures"].append("losing same-owner request must return scan_admission_busy")
        result["passed"] = not result["failures"]
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--targets", required=True, help='JSON array of {"email","url","project_id"}')
    parser.add_argument("--tokens", required=True, help='JSON object mapping email to bearer token')
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--double-submit", action="store_true")
    parser.add_argument("--timeout", type=int, default=2400)
    parser.add_argument("--gcp-project", default="")
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
