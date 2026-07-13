#!/usr/bin/env python3
"""Post-deploy beta acceptance scans (Shopify / Signal / Basecamp).

This is the Phase 1 "perform the three acceptance scans" gate. It runs the
named sites through the scan + review pipeline and checks each result against
the crawler contract (``validate_crawler_contract``). Every site must complete
and pass for the run to recommend freezing the beta crawler.

Two modes:

  * HTTP (default): hit a *deployed* scanner's ``/scan`` and ``/review``
    endpoints. This is what actually verifies the deployed revision.

        python scripts/run_beta_acceptance_scans.py \\
            --scanner-url https://scanner.example.run.app \\
            --report-output ../docs/beta-acceptance.md

  * In-process (``--in-process``): run the pipeline directly in this process.
    Useful for a local dry run without a deployed URL, but it does NOT prove a
    deployed revision is healthy.

Records stream to a JSONL file and a markdown report after every site, so a
long run leaves partial evidence even if it is interrupted. Exit code is 0 only
when the acceptance run passes.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

SCANNER_API_ROOT = Path(__file__).resolve().parents[1]
if str(SCANNER_API_ROOT) not in sys.path:
    sys.path.insert(0, str(SCANNER_API_ROOT))

from app.crawler_acceptance import (  # noqa: E402
    build_acceptance_record,
    format_acceptance_markdown,
    summarize_beta_acceptance,
)

DEFAULT_MANIFEST = SCANNER_API_ROOT.parent / "data" / "beta-acceptance-manifest.jsonl"
DEFAULT_OUTPUT = SCANNER_API_ROOT.parent / "data" / "beta-acceptance-records.jsonl"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    records: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: each line must contain an object")
        records.append(value)
    return records


def normalize_manifest(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        site = str(record.get("site") or "").strip()
        url = str(record.get("url") or "").strip()
        scan_mode = str(record.get("scan_mode") or "advanced").strip().lower()
        if not site or site in seen:
            raise ValueError(f"manifest site must be unique and non-empty: {site!r}")
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"manifest URL must be absolute: {url!r}")
        if scan_mode not in {"basic", "quick", "deep", "advanced"}:
            raise ValueError(f"invalid scan mode for {site}: {scan_mode}")
        seen.add(site)
        normalized.append({
            **record,
            "site": site,
            "url": url,
            "stratum": str(record.get("stratum") or "").strip(),
            "scan_mode": scan_mode,
            "path_prefix": str(record.get("path_prefix") or "").strip() or None,
        })
    if not normalized:
        raise ValueError("manifest is empty")
    return normalized


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


async def run_pipeline_in_process(record: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    from app.indexability_postprocess import apply_indexability_quality_to_result
    from app.render_evidence_quality import apply_render_evidence_quality
    from app.review import run_review
    from app.review_calibration import apply_review_evidence_calibration
    from app.scanner import run_scan
    from app.trust_discovery import apply_trust_discovery_gate, enrich_scan_with_trust_pages

    scan = await run_scan(
        website_url=record["url"],
        path_prefix=record.get("path_prefix"),
        scan_mode=record["scan_mode"],
    )
    scan = await enrich_scan_with_trust_pages(scan)
    scan = apply_indexability_quality_to_result(scan)
    scan = apply_render_evidence_quality(scan)

    review = run_review(scan)
    review = apply_trust_discovery_gate(review, scan)
    review = apply_review_evidence_calibration(review, scan)
    return scan, review


async def run_pipeline_http(
    record: dict[str, Any],
    *,
    scanner_url: str,
    api_key: str,
    timeout_seconds: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    headers = {"x-scanner-key": api_key} if api_key else {}
    payload = {
        "website_url": record["url"],
        "path_prefix": record.get("path_prefix"),
        "scan_mode": record["scan_mode"],
    }
    async with httpx.AsyncClient(base_url=scanner_url.rstrip("/"), timeout=timeout_seconds) as client:
        scan_response = await client.post("/scan", json=payload, headers=headers)
        scan_response.raise_for_status()
        scan = scan_response.json()

        review_response = await client.post("/review", json=scan, headers=headers)
        review_response.raise_for_status()
        review = review_response.json()
    return scan, review


async def validate_site(
    record: dict[str, Any],
    *,
    in_process: bool,
    scanner_url: str,
    api_key: str,
    timeout_seconds: float,
) -> tuple[dict | None, dict | None]:
    started = time.monotonic()
    try:
        if in_process:
            coro = run_pipeline_in_process(record)
        else:
            coro = run_pipeline_http(
                record,
                scanner_url=scanner_url,
                api_key=api_key,
                timeout_seconds=timeout_seconds,
            )
        scan, review = await asyncio.wait_for(coro, timeout=max(30.0, timeout_seconds))
        duration = time.monotonic() - started
        acceptance = build_acceptance_record(record, scan, review, duration_seconds=duration)
        return acceptance, None
    except asyncio.TimeoutError:
        return None, {
            "site": record["site"],
            "url": record["url"],
            "stratum": record["stratum"],
            "error": f"acceptance pipeline exceeded {timeout_seconds:.0f} seconds",
            "error_type": "timeout",
        }
    except Exception as exc:  # noqa: BLE001 - record any failure as evidence
        return None, {
            "site": record["site"],
            "url": record["url"],
            "stratum": record["stratum"],
            "error": str(exc)[:500],
            "error_type": type(exc).__name__,
        }


async def collect(
    manifest: list[dict[str, Any]],
    *,
    in_process: bool,
    scanner_url: str,
    api_key: str,
    timeout_seconds: float,
    output: Path,
    failure_output: Path,
    report_output: Path,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for index, record in enumerate(manifest, start=1):
        sys.stdout.write(f"[{index}/{len(manifest)}] scanning {record['site']} ({record['url']})\n")
        sys.stdout.flush()
        acceptance, failure = await validate_site(
            record,
            in_process=in_process,
            scanner_url=scanner_url,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )
        if acceptance is not None:
            records.append(acceptance)
            validation = acceptance.get("validation") or {}
            sys.stdout.write(
                "  completed: pages={pages}, score={score}, contract={contract}\n".format(
                    pages=acceptance.get("pages_crawled", 0),
                    score=acceptance.get("health_score", "—"),
                    contract="pass" if validation.get("passed") else "fail",
                )
            )
        elif failure is not None:
            failures.append(failure)
            sys.stdout.write(f"  failed: {failure.get('error')}\n")

        write_jsonl(output, records)
        write_jsonl(failure_output, failures)
        summary = summarize_beta_acceptance(records, failures)
        report_output.parent.mkdir(parents=True, exist_ok=True)
        report_output.write_text(format_acceptance_markdown(summary), encoding="utf-8")
        sys.stdout.flush()

    return summarize_beta_acceptance(records, failures)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--failure-output", type=Path)
    parser.add_argument("--report-output", type=Path, required=True)
    parser.add_argument(
        "--scanner-url",
        default=os.getenv("SCANNER_URL", ""),
        help="Base URL of the deployed scanner (required unless --in-process).",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("SCANNER_API_KEY", ""),
        help="Value sent as the x-scanner-key header. Defaults to $SCANNER_API_KEY.",
    )
    parser.add_argument(
        "--in-process",
        action="store_true",
        help="Run the pipeline locally instead of against a deployed scanner.",
    )
    parser.add_argument("--timeout", type=float, default=210.0, help="Per-site timeout in seconds.")
    args = parser.parse_args()

    if not args.in_process and not args.scanner_url:
        parser.error("--scanner-url is required unless --in-process is set")

    failure_output = args.failure_output or args.output.with_name(
        f"{args.output.stem}.failures{args.output.suffix or '.jsonl'}"
    )

    try:
        manifest = normalize_manifest(load_jsonl(args.manifest))
        summary = asyncio.run(
            collect(
                manifest,
                in_process=args.in_process,
                scanner_url=args.scanner_url,
                api_key=args.api_key,
                timeout_seconds=max(30.0, args.timeout),
                output=args.output,
                failure_output=failure_output,
                report_output=args.report_output,
            )
        )
    except (OSError, TypeError, ValueError) as exc:
        parser.error(str(exc))

    sys.stdout.write(json.dumps({
        "requested_sites": summary["requested_sites"],
        "completed_sites": summary["completed_sites"],
        "failed_sites": summary["failed_sites"],
        "contract_passed_sites": summary["contract_passed_sites"],
        "acceptance_passed": summary["acceptance_passed"],
        "freeze_recommendation": summary["freeze_recommendation"],
        "recurring_contract_violations": summary["recurring_contract_violations"],
        "output": str(args.output),
        "failure_output": str(failure_output),
        "report_output": str(args.report_output),
    }, indent=2) + "\n")
    return 0 if summary["acceptance_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
