#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import httpx


SCANNER_API_ROOT = Path(__file__).resolve().parents[1]
if str(SCANNER_API_ROOT) not in sys.path:
    sys.path.insert(0, str(SCANNER_API_ROOT))

from app.render_risk_collection import (  # noqa: E402
    fetch_study_record,
    normalize_manifest_record,
)


def load_jsonl(path: Path, *, required: bool = True) -> list[dict]:
    if not path.exists():
        if required:
            raise FileNotFoundError(path)
        return []

    records: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc.msg}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: each line must contain a JSON object")
            records.append(value)
    return records


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    content = "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records)
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def default_failure_path(output: Path) -> Path:
    suffix = output.suffix or ".jsonl"
    return output.with_name(f"{output.stem}.failures{suffix}")


async def collect(
    manifest: list[dict],
    *,
    scanner_url: str,
    scanner_key: str,
    timeout_seconds: float,
    attempts: int,
    concurrency: int,
) -> list[tuple[dict | None, dict | None]]:
    semaphore = asyncio.Semaphore(max(1, min(int(concurrency or 1), 5)))

    async with httpx.AsyncClient(follow_redirects=False) as client:
        async def run(record: dict) -> tuple[dict | None, dict | None]:
            async with semaphore:
                return await fetch_study_record(
                    client,
                    scanner_url,
                    scanner_key,
                    record,
                    timeout_seconds=timeout_seconds,
                    attempts=attempts,
                )

        return await asyncio.gather(*(run(record) for record in manifest))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Collect scanner-produced render_evidence for the stratified renderer-risk study. "
            "Successful records and failed scans are written to separate JSONL files."
        )
    )
    parser.add_argument("manifest", type=Path, help="JSONL manifest containing site, url, and stratum")
    parser.add_argument("output", type=Path, help="JSONL output for successful study records")
    parser.add_argument(
        "--failure-output",
        type=Path,
        help="JSONL output for failed scans (default: <output>.failures.jsonl)",
    )
    parser.add_argument(
        "--scanner-url",
        default=os.getenv("SCANNER_API_URL") or os.getenv("PYTHON_SCANNER_API_URL") or "",
        help="Python scanner base URL (default: SCANNER_API_URL)",
    )
    parser.add_argument(
        "--scanner-key-env",
        default="SCANNER_API_KEY",
        help="Environment variable containing the scanner key (default: SCANNER_API_KEY)",
    )
    parser.add_argument("--timeout", type=float, default=120.0, help="Per-attempt timeout in seconds")
    parser.add_argument("--attempts", type=int, default=2, help="Maximum attempts per site (1-5)")
    parser.add_argument("--concurrency", type=int, default=1, help="Concurrent sites (1-5; default: 1)")
    parser.add_argument(
        "--retry-failures",
        action="store_true",
        help="Retry sites already present in the failure output",
    )
    args = parser.parse_args()

    scanner_key = os.getenv(args.scanner_key_env, "")
    if not args.scanner_url:
        parser.error("--scanner-url or SCANNER_API_URL is required")
    if not scanner_key:
        parser.error(f"{args.scanner_key_env} is not configured")

    failure_output = args.failure_output or default_failure_path(args.output)

    try:
        manifest = [normalize_manifest_record(record) for record in load_jsonl(args.manifest)]
        existing_successes = load_jsonl(args.output, required=False)
        existing_failures = load_jsonl(failure_output, required=False)
    except (OSError, TypeError, ValueError) as exc:
        parser.error(str(exc))

    by_site: dict[str, dict] = {}
    ordered_sites: list[str] = []
    for record in manifest:
        site = record["site"]
        if site in by_site:
            parser.error(f"duplicate site in manifest: {site}")
        by_site[site] = record
        ordered_sites.append(site)

    successes = {
        str(record.get("site") or "").strip(): record
        for record in existing_successes
        if str(record.get("site") or "").strip() in by_site
    }
    failures = {
        str(record.get("site") or "").strip(): record
        for record in existing_failures
        if str(record.get("site") or "").strip() in by_site
    }

    pending = [
        by_site[site]
        for site in ordered_sites
        if site not in successes and (args.retry_failures or site not in failures)
    ]

    if pending:
        results = asyncio.run(
            collect(
                pending,
                scanner_url=args.scanner_url,
                scanner_key=scanner_key,
                timeout_seconds=max(1.0, args.timeout),
                attempts=max(1, min(args.attempts, 5)),
                concurrency=max(1, min(args.concurrency, 5)),
            )
        )
        for manifest_record, (study_record, failure_record) in zip(pending, results):
            site = manifest_record["site"]
            if study_record is not None:
                successes[site] = study_record
                failures.pop(site, None)
            elif failure_record is not None:
                failures[site] = failure_record

    success_records = [successes[site] for site in ordered_sites if site in successes]
    failure_records = [failures[site] for site in ordered_sites if site in failures and site not in successes]
    write_jsonl(args.output, success_records)
    write_jsonl(failure_output, failure_records)

    summary = {
        "manifest_sites": len(ordered_sites),
        "successful_sites": len(success_records),
        "failed_sites": len(failure_records),
        "pending_sites": len(ordered_sites) - len(success_records) - len(failure_records),
        "output": str(args.output),
        "failure_output": str(failure_output),
    }
    sys.stdout.write(json.dumps(summary, indent=2) + "\n")
    return 1 if failure_records else 0


if __name__ == "__main__":
    raise SystemExit(main())
