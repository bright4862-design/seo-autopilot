#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

POLICY_ID = "b25_standard150_robots_respected_v1"
SCOPE = "full_site_same_origin"
PUBLIC_SCAN_MODE = "standard_150"
PYTHON_SCAN_MODE = "advanced"
CRAWL_BUDGET_SECONDS = 210

RUNNER = r'''
import asyncio
import json
import sys
import traceback
from pathlib import Path

url, site_id, stratum, output_path = sys.argv[1:5]

from app.beta_revision import live_revision
from app.main import apply_post_crawl_transforms
from app.scan_job import build_local_review
from app.scanner import run_scan
from app.trust_discovery import enrich_scan_with_trust_pages

async def execute():
    scan = await asyncio.wait_for(
        run_scan(
            website_url=url,
            path_prefix=None,
            scan_mode="advanced",
            timeout_seconds=210,
            job_mode=True,
        ),
        timeout=240,
    )
    try:
        scan = await asyncio.wait_for(enrich_scan_with_trust_pages(scan), timeout=10)
    except asyncio.TimeoutError:
        warnings = list(scan.get("crawl_warnings") or [])
        warnings.append("B25 local capture: bounded trust-page discovery timed out; crawl evidence preserved.")
        scan["crawl_warnings"] = warnings
    scan = apply_post_crawl_transforms(scan)
    scan["beta_revision_fingerprint"] = live_revision()["fingerprint"]
    review = build_local_review(scan)
    review["beta_revision_fingerprint"] = live_revision()["fingerprint"]
    return scan, review

payload = {
    "site_id": site_id,
    "url": url,
    "stratum": stratum,
    "runner": {
        "scan_mode": "standard_150",
        "python_scan_mode": "advanced",
        "crawl_budget_seconds": 210,
        "job_mode": True,
        "robots_respected": True,
    },
}
try:
    scan, review = asyncio.run(execute())
    payload["capture_status"] = "completed"
    payload["scan"] = scan
    payload["review"] = review
except Exception as exc:
    payload["capture_status"] = "error"
    payload["error_type"] = type(exc).__name__
    payload["error"] = str(exc)[:1000]
    payload["traceback"] = traceback.format_exc(limit=8)[-6000:]

payload["release_fingerprint"] = live_revision()["fingerprint"]
Path(output_path).write_text(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
'''

def canonical_json(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

def run_source(*, checkout: Path, python_bin: Path, source_sha: str, site_id: str, url: str, stratum: str, label: str, out_dir: Path) -> dict:
    scanner_root = checkout / "scanner-api"
    raw_path = out_dir / f"{label}-raw.json"
    runner_path = out_dir / f"{label}-runner.py"
    runner_path.write_text(RUNNER, encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(scanner_root)
    env["WORKER_SOURCE_SHA"] = source_sha
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [str(python_bin), str(runner_path), url, site_id, stratum, str(raw_path)],
        cwd=scanner_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=300,
        check=False,
    )
    if not raw_path.exists():
        raise RuntimeError(
            f"{label} capture infrastructure failed rc={completed.returncode}: "
            f"{(completed.stderr or completed.stdout)[-2000:]}"
        )

    raw_bytes = raw_path.read_bytes()
    raw = json.loads(raw_bytes.decode("utf-8"))
    captured_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    release_fingerprint = str(raw.get("release_fingerprint") or "").strip()
    evidence_bundle_id = hashlib.sha256(
        f"{source_sha}|{site_id}|{captured_at}|{hashlib.sha256(raw_bytes).hexdigest()}".encode("utf-8")
    ).hexdigest()[:32]

    envelope = {
        "provenance": "captured",
        "artifact_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "source_sha": source_sha,
        "release_fingerprint": release_fingerprint,
        "captured_at": captured_at,
        "scan_mode": PUBLIC_SCAN_MODE,
        "scope": SCOPE,
        "policy_id": POLICY_ID,
        "evidence_bundle_id": evidence_bundle_id,
        "capture_status": str(raw.get("capture_status") or "unknown"),
        "raw_file": raw_path.name,
        "process_returncode": completed.returncode,
    }
    (out_dir / f"{label}-capture.json").write_bytes(canonical_json(envelope))
    (out_dir / f"{label}-stdout.txt").write_text(completed.stdout or "", encoding="utf-8")
    (out_dir / f"{label}-stderr.txt").write_text(completed.stderr or "", encoding="utf-8")
    return envelope

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-checkout", type=Path, required=True)
    parser.add_argument("--candidate-checkout", type=Path, required=True)
    parser.add_argument("--baseline-python", type=Path, required=True)
    parser.add_argument("--candidate-python", type=Path, required=True)
    parser.add_argument("--baseline-sha", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--site-id", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--stratum", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    baseline = run_source(
        checkout=args.baseline_checkout,
        python_bin=args.baseline_python,
        source_sha=args.baseline_sha,
        site_id=args.site_id,
        url=args.url,
        stratum=args.stratum,
        label="baseline",
        out_dir=args.output_dir,
    )
    candidate = run_source(
        checkout=args.candidate_checkout,
        python_bin=args.candidate_python,
        source_sha=args.candidate_sha,
        site_id=args.site_id,
        url=args.url,
        stratum=args.stratum,
        label="candidate",
        out_dir=args.output_dir,
    )

    pair = {
        "site_id": args.site_id,
        "url": args.url,
        "stratum": args.stratum,
        "baseline": baseline,
        "candidate": candidate,
    }
    (args.output_dir / "pair-metadata.json").write_bytes(canonical_json(pair))

    if len(baseline.get("release_fingerprint", "")) != 16:
        print("::error::baseline release fingerprint is missing or invalid", file=sys.stderr)
        return 2
    if len(candidate.get("release_fingerprint", "")) != 16:
        print("::error::candidate release fingerprint is missing or invalid", file=sys.stderr)
        return 2
    if candidate["captured_at"] < baseline["captured_at"]:
        print("::error::candidate capture timestamp precedes baseline", file=sys.stderr)
        return 2

    print(json.dumps({
        "site_id": args.site_id,
        "baseline_status": baseline["capture_status"],
        "candidate_status": candidate["capture_status"],
        "baseline_fingerprint": baseline["release_fingerprint"],
        "candidate_fingerprint": candidate["release_fingerprint"],
        "baseline_artifact_sha256": baseline["artifact_sha256"],
        "candidate_artifact_sha256": candidate["artifact_sha256"],
    }, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
