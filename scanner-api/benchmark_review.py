#!/usr/bin/env python3
"""Offline review scaling benchmark and immutable-revision fixture hashes.

Synthetic timing is a local smoke benchmark, not production corpus calibration.
Every size runs in a fresh process with a bounded wall time. No URLs are fetched.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import tarfile
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]


def synthetic_payload(size):
    if not 1 <= size <= 5000:
        raise ValueError("Synthetic size must be between 1 and 5000")
    origin = "https://benchmark.example"
    pages = []
    for index in range(size):
        section = ("solutions", "products", "insights", "stores")[index % 4]
        url = f"{origin}/{section}/page-{index}"
        pages.append({
            "url": url, "final_url": url, "path": f"/{section}/page-{index}",
            "status_code": 200, "content_type": "text/html", "indexable": True,
            "indexability_state": "indexable", "page_evidence_class": "content",
            "title": f"Example {section} page {index}", "h1": f"Example {section} {index}",
            "h1_count": 1, "meta_description": "" if index % 3 == 0 else f"Description of example {index}",
            "canonical": url, "word_count": 400 + index % 100, "image_count": 8,
            "image_missing_alt_count": 2 if index % 5 == 0 else 0,
            "page_template_family": "article_page" if section == "insights" else "standard",
            "estimated_page_intent": "blog" if section == "insights" else "money",
            "discovered_from": "sitemap", "source_pages": [f"{origin}/{section}"],
        })
    return {
        "success": True, "website_url": origin, "final_url": origin,
        "normalized_domain": "benchmark.example", "pages_crawled": size,
        "pages_found": size, "queued_remaining": 0, "pages": pages,
        "grouped_findings": [], "scan_deadline_reached": False,
        "scan_summary": {"pages_crawled": size, "pages_found": size},
    }


def measure_one(size):
    from app.review import run_review
    from app.scan_job import build_completion_envelope

    payload = synthetic_payload(size)
    encoded_pages = [len(json.dumps(page, sort_keys=True, separators=(",", ":")).encode())
                     for page in payload["pages"]]
    started = time.perf_counter()
    result = run_review(payload)
    elapsed = time.perf_counter() - started
    envelope = build_completion_envelope({"id": "benchmark-scan", "owner_user_id": "benchmark-owner",
        "project_id": "benchmark-project", "request_id": "benchmark-request", "attempt_count": 1},
        payload, result, "synthetic-benchmark-key")
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {
        "pages": size, "review_seconds": round(elapsed, 6),
        "page_evidence_total_bytes": sum(encoded_pages),
        "page_evidence_mean_bytes": round(sum(encoded_pages) / size, 2),
        "review_output_bytes": len(json.dumps(result, sort_keys=True, separators=(",", ":")).encode()),
        "completion_envelope_bytes": len(json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()),
        "process_peak_rss_bytes": rss if sys.platform == "darwin" else rss * 1024,
        "memory_scope": "fresh review/envelope process high-water RSS including imports and payload; excludes worker parent",
        "success": result.get("success") is True,
    }


def benchmark(sizes, timeout):
    results = []
    for size in sizes:
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--one-size", str(size)],
                check=True, capture_output=True, text=True, timeout=timeout,
            )
            row = json.loads(completed.stdout)
            row["subprocess_wall_seconds"] = round(time.perf_counter() - started, 6)
            row["within_wall_timeout"] = True
        except subprocess.TimeoutExpired:
            row = {"pages": size, "success": False, "within_wall_timeout": False,
                   "error": "review_process_wall_timeout"}
        except subprocess.CalledProcessError as exc:
            row = {"pages": size, "success": False, "error": "review_process_failed",
                   "detail": exc.stderr[-2000:]}
        results.append(row)
    return results


def capture_goldens(revision):
    """Hash review results using modules exported from one immutable commit.

    This characterizes the recorded scan fixture -> review seam only. It does
    not claim scanner-fetch parity or freeze volatile live crawl timings.
    """
    commit = subprocess.run(["git", "rev-parse", "--verify", f"{revision}^{{commit}}"], cwd=ROOT,
                            capture_output=True, text=True, check=True).stdout.strip()
    archive = subprocess.run(["git", "archive", commit, "scanner-api/app", "tests/fixtures"],
                             cwd=ROOT, capture_output=True, check=True).stdout
    with tempfile.TemporaryDirectory(prefix="fixlist-review-baseline-") as temp:
        with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
            bundle.extractall(temp, filter="data")
        code = """
import hashlib, json, pathlib, sys
from app.review import run_review
rows = []
for path in sorted(pathlib.Path(sys.argv[1]).glob('*.scan.json')):
    raw = path.read_bytes()
    review = run_review(json.loads(raw))
    canonical = json.dumps(review, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    rows.append({'fixture': path.name, 'input_sha256': hashlib.sha256(raw).hexdigest(),
                 'review_sha256': hashlib.sha256(canonical).hexdigest(), 'review_bytes': len(canonical)})
print(json.dumps(rows))
"""
        env = dict(os.environ, PYTHONPATH=str(Path(temp) / "scanner-api"))
        run = subprocess.run([sys.executable, "-c", code, str(Path(temp) / "tests/fixtures")],
                             cwd=temp, env=env, check=True, capture_output=True, text=True, timeout=60)
    return {"source_commit": commit, "scope": "recorded scanner fixture to review only",
            "canonicalization": "JSON sorted keys, compact separators, UTF-8, ensure_ascii=False",
            "fixtures": json.loads(run.stdout)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", nargs="+", type=int, default=[150, 500, 1000])
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--capture-goldens", metavar="REVISION")
    parser.add_argument("--one-size", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.one_size is not None:
        print(json.dumps(measure_one(args.one_size)))
        return 0
    if args.timeout <= 0 or any(not 1 <= size <= 5000 for size in args.sizes):
        parser.error("Timeout must be positive and sizes must be between 1 and 5000")
    if args.capture_goldens:
        report = capture_goldens(args.capture_goldens)
    else:
        report = {
            "benchmark": "synthetic_review_scaling_v1", "wall_timeout_seconds": args.timeout,
            "limitations": "Synthetic local evidence, not representative production HTML or a 50-site calibration; excludes crawl and finalize memory.",
            "results": benchmark(args.sizes, args.timeout),
        }
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if all(row.get("success") for row in report.get("results", [])) else 1


if __name__ == "__main__":
    raise SystemExit(main())
