#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any


SCANNER_API_ROOT = Path(__file__).resolve().parents[1]
if str(SCANNER_API_ROOT) not in sys.path:
    sys.path.insert(0, str(SCANNER_API_ROOT))

from app.crawler_acceptance import (  # noqa: E402
    REQUIRED_STRATA,
    build_acceptance_record,
    format_acceptance_markdown,
    summarize_acceptance,
)
from app.indexability_postprocess import apply_indexability_quality_to_result  # noqa: E402
from app.render_evidence_quality import apply_render_evidence_quality  # noqa: E402
from app.review import run_review  # noqa: E402
from app.review_calibration import apply_review_evidence_calibration  # noqa: E402
from app.scanner import run_scan  # noqa: E402
from app.trust_discovery import (  # noqa: E402
    apply_trust_discovery_gate,
    enrich_scan_with_trust_pages,
)


def load_jsonl(path: Path, *, required: bool = True) -> list[dict[str, Any]]:
    if not path.exists():
        if required:
            raise FileNotFoundError(path)
        return []
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


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def normalize_manifest(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    strata: dict[str, int] = {}
    for record in records:
        site = str(record.get("site") or "").strip()
        url = str(record.get("url") or "").strip()
        stratum = str(record.get("stratum") or "").strip()
        scan_mode = str(record.get("scan_mode") or "advanced").strip().lower()
        if not site or site in seen:
            raise ValueError(f"manifest site must be unique and non-empty: {site!r}")
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"manifest URL must be absolute: {url!r}")
        if stratum not in REQUIRED_STRATA:
            raise ValueError(f"invalid stratum for {site}: {stratum}")
        if scan_mode not in {"basic", "quick", "deep", "advanced"}:
            raise ValueError(f"invalid scan mode for {site}: {scan_mode}")
        seen.add(site)
        strata[stratum] = strata.get(stratum, 0) + 1
        normalized.append({
            **record,
            "site": site,
            "url": url,
            "stratum": stratum,
            "scan_mode": scan_mode,
            "path_prefix": str(record.get("path_prefix") or "").strip() or None,
        })
    if len(normalized) != 9 or any(strata.get(stratum, 0) != 3 for stratum in REQUIRED_STRATA):
        raise ValueError(f"manifest must contain exactly 9 sites and 3 per stratum: {strata}")
    return normalized


async def run_pipeline(record: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
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


async def validate_site(record: dict[str, Any], timeout_seconds: float) -> tuple[dict | None, dict | None]:
    started = time.monotonic()
    try:
        scan, review = await asyncio.wait_for(
            run_pipeline(record),
            timeout=max(30.0, float(timeout_seconds)),
        )
        duration = time.monotonic() - started
        acceptance = build_acceptance_record(
            record,
            scan,
            review,
            duration_seconds=duration,
        )
        return acceptance, None
    except asyncio.TimeoutError:
        return None, {
            "site": record["site"],
            "url": record["url"],
            "stratum": record["stratum"],
            "error": f"validation pipeline exceeded {timeout_seconds:.0f} seconds",
            "error_type": "timeout",
        }
    except Exception as exc:
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
    timeout_seconds: float,
    output: Path,
    failure_output: Path,
    report_output: Path,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for index, record in enumerate(manifest, start=1):
        sys.stdout.write(
            f"[{index}/{len(manifest)}] validating {record['site']} ({record['stratum']})\n"
        )
        sys.stdout.flush()
        acceptance, failure = await validate_site(record, timeout_seconds)
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
        summary = summarize_acceptance(manifest, records, failures)
        report_output.parent.mkdir(parents=True, exist_ok=True)
        report_output.write_text(format_acceptance_markdown(summary), encoding="utf-8")
        sys.stdout.flush()

    return summarize_acceptance(manifest, records, failures)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the final balanced FixList crawler and Python Review acceptance validation."
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--failure-output", type=Path)
    parser.add_argument("--report-output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=210.0, help="Per-site pipeline timeout")
    args = parser.parse_args()

    failure_output = args.failure_output or args.output.with_name(
        f"{args.output.stem}.failures{args.output.suffix or '.jsonl'}"
    )
    try:
        manifest = normalize_manifest(load_jsonl(args.manifest))
        summary = asyncio.run(
            collect(
                manifest,
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
