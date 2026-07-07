"""Live benchmark runner — run where open network is available (local or deployed).

Calls the scanner in-process against real sites, measures wall-clock time, and
scores each against the Deno baseline. This makes live network calls, so it does
NOT install the offline test stub.

Usage:
    cd scanner-api
    pip install -r requirements.txt
    python benchmark.py                 # all sites
    python benchmark.py pretto          # one site
"""
import asyncio
import sys
import time

from app.scanner import run_scan

# name -> (start_url, path_prefix, deno_baseline)
# Deno baseline for Pretto is the known-bad run: 9 pages / 0 findings / 500 artifacts.
SITES = {
    "pretto": ("https://www.pretto.fr/pret-immobilier/", "/pret-immobilier", {"pages": 9, "findings": 0, "artifacts": 500}),
    "meilleurtaux": ("https://www.meilleurtaux.fr/assurance/", "/assurance", None),
    "funbooker": ("https://www.funbooker.com/", "/", None),
    "centerstreet": ("https://www.centerstreetlending.com/", "/", None),
}


def in_scope(pages, prefix):
    if not prefix or prefix == "/":
        return len(pages)
    return sum(1 for p in pages if str(p.get("path") or "/").startswith(prefix))


async def bench_one(name, start, prefix, baseline):
    t0 = time.monotonic()
    result = await run_scan(start, path_prefix=prefix, scan_mode="advanced", concurrency=8)
    elapsed = time.monotonic() - t0

    if not result.get("success"):
        print(f"  {name:14s} FAILED: {result.get('error')}")
        return

    pages = result.get("pages", [])
    scoped = in_scope(pages, prefix)
    findings = len(result.get("recommendations", []))
    artifacts = result.get("suspicious_url_artifact_count", 0)

    print(f"  {name:14s} pages={len(pages):4d}  in_scope={scoped:4d}  findings={findings:4d}  artifacts={artifacts:4d}  {elapsed:6.1f}s")

    if baseline:
        beats = (
            scoped > baseline["pages"]
            and findings > 0
            and artifacts <= 50
        )
        checks = [
            f"in-scope > {baseline['pages']}: {'PASS' if scoped > baseline['pages'] else 'FAIL'} ({scoped})",
            f"findings > 0: {'PASS' if findings > 0 else 'FAIL'} ({findings})",
            f"artifacts <= 50: {'PASS' if artifacts <= 50 else 'FAIL'} ({artifacts})",
        ]
        print("                 vs Deno baseline (9/0/500):")
        for c in checks:
            print(f"                   - {c}")
        print(f"                 VERDICT: {'PYTHON BEATS DENO' if beats else 'DOES NOT BEAT DENO YET'} "
              f"(check wall-clock {elapsed:.1f}s is similar or better)")


async def main(selected):
    names = selected or list(SITES.keys())
    print("Live benchmark — scanner-api (concurrency=8)\n")
    for name in names:
        if name not in SITES:
            print(f"  unknown site: {name}")
            continue
        start, prefix, baseline = SITES[name]
        try:
            await bench_one(name, start, prefix, baseline)
        except Exception as exc:  # noqa: BLE001
            print(f"  {name:14s} ERROR: {exc}")
        print()


if __name__ == "__main__":
    asyncio.run(main([a.lower() for a in sys.argv[1:]]))
