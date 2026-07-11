#!/usr/bin/env python3
"""Measure how sitemap order skews the scanner's current FIFO page sample.

This is read-only instrumentation. It fetches sitemap URLs through the same
loader used by the production scanner, classifies them with the production
template classifier, and compares the whole sitemap distribution with the
first URLs the current FIFO frontier would claim.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.extract import classify_template
from app.scanner import SCAN_BUDGETS, normalize_prefix, normalize_url
from app.sitemap import load_sitemap_urls


DEFAULT_SITEMAP_LIMIT = 100_000
TRUST_FAMILIES = {"contact", "legal_info"}
TRUST_PATH_TOKENS = (
    "/about",
    "/a-propos",
    "/contact",
    "/privacy",
    "/confidentialite",
    "/terms",
    "/conditions",
    "/security",
    "/legal",
    "/mentions-legales",
    "/cgv",
)


@dataclass(frozen=True)
class FamilyRow:
    family: str
    sitemap_count: int
    sample_count: int
    proportional_target: float
    flag: str


def is_trust_url(url: str) -> bool:
    path = (urlparse(url).path or "/").lower().rstrip("/")
    family = classify_template(path)
    return family in TRUST_FAMILIES or any(
        path == token or path.startswith(f"{token}/") for token in TRUST_PATH_TOKENS
    )


def simulate_fifo_sample(start_url: str, sitemap_urls: list[str], max_pages: int) -> list[str]:
    """Mirror the initial production queue: seed first, then sitemap order."""
    ordered: list[str] = []
    seen: set[str] = set()
    for url in [start_url, *sitemap_urls]:
        clean = normalize_url(url)
        if clean and clean not in seen:
            seen.add(clean)
            ordered.append(clean)
        if len(ordered) >= max_pages:
            break
    return ordered


def family_counts(urls: list[str]) -> Counter[str]:
    return Counter(classify_template(urlparse(url).path or "/") for url in urls)


def distribution_rows(sitemap_urls: list[str], sampled_urls: list[str]) -> list[FamilyRow]:
    sitemap = family_counts(sitemap_urls)
    sample = family_counts(sampled_urls)
    sitemap_total = max(1, sum(sitemap.values()))
    sample_total = len(sampled_urls)
    rows: list[FamilyRow] = []

    for family in sorted(sitemap, key=lambda item: (-sitemap[item], item)):
        expected = sitemap[family] / sitemap_total * sample_total
        actual = sample[family]
        if actual == 0:
            flag = "NEVER SAMPLED"
        elif sitemap[family] >= 3 and actual == 1:
            flag = "SINGLE REPRESENTATIVE"
        elif expected >= 2 and actual < expected * 0.5:
            flag = "under-sampled"
        elif expected >= 1 and actual > expected * 1.5:
            flag = "over-sampled"
        else:
            flag = ""
        rows.append(FamilyRow(family, sitemap[family], actual, expected, flag))
    return rows


def print_report(website_url: str, sitemap_urls: list[str], sampled_urls: list[str]) -> None:
    sitemap_trust = [url for url in sitemap_urls if is_trust_url(url)]
    sampled_set = set(sampled_urls)
    sampled_trust = [url for url in sitemap_trust if normalize_url(url) in sampled_set]

    print(f"Website: {website_url}")
    print(f"Sitemap URLs loaded: {len(sitemap_urls)}")
    print(f"FIFO sample simulated: {len(sampled_urls)}")
    print()
    print(f"{'family':<28} {'sitemap':>8} {'sample':>8} {'target':>8}  flag")
    print("-" * 76)
    for row in distribution_rows(sitemap_urls, sampled_urls):
        print(
            f"{row.family:<28} {row.sitemap_count:>8} {row.sample_count:>8} "
            f"{row.proportional_target:>8.1f}  {row.flag}"
        )

    print()
    print(f"Trust/legal URLs in sitemap: {len(sitemap_trust)}")
    print(f"Trust/legal URLs in FIFO sample: {len(sampled_trust)}")
    if sitemap_trust and not sampled_trust:
        print("WARNING: trust/legal pages exist in the sitemap but are absent from the sample.")
    for url in sitemap_trust[:20]:
        marker = "sampled" if normalize_url(url) in sampled_set else "missed"
        print(f"  [{marker}] {url}")

    singletons = [
        row for row in distribution_rows(sitemap_urls, sampled_urls)
        if row.flag == "SINGLE REPRESENTATIVE"
    ]
    if singletons:
        print()
        print("Families with one sampled representative despite multiple sitemap URLs:")
        for row in singletons:
            print(f"  {row.family}: 1 of {row.sitemap_count}")


async def measure(args: argparse.Namespace) -> int:
    start_url = normalize_url(args.website_url)
    if not start_url:
        raise SystemExit("website_url must be a valid HTTP(S) URL")

    parsed = urlparse(start_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    prefix = normalize_prefix(args.path_prefix or parsed.path or "/")
    artifacts: list[dict] = []

    async with httpx.AsyncClient(
        timeout=args.timeout,
        follow_redirects=False,
        headers={"User-Agent": "Mozilla/5.0 (compatible; FixListSamplingAudit/1.0)"},
    ) as client:
        sitemap_urls = await load_sitemap_urls(
            client,
            origin,
            prefix,
            args.sitemap_limit,
            artifacts,
        )

    if not sitemap_urls:
        print(f"Website: {start_url}")
        print("No sitemap URLs were found. The production scanner will rely on link-discovery BFS.")
        return 2

    sampled_urls = simulate_fifo_sample(start_url, sitemap_urls, args.max_pages)
    print_report(start_url, sitemap_urls, sampled_urls)
    if artifacts:
        print()
        print(f"Suspicious sitemap artifacts excluded: {len(artifacts)}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare sitemap template distribution with the scanner's current FIFO sample."
    )
    parser.add_argument("website_url")
    parser.add_argument("--path-prefix", default="")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=SCAN_BUDGETS["advanced"]["max_pages"],
        help="Sample size to simulate (default: advanced scan budget).",
    )
    parser.add_argument("--sitemap-limit", type=int, default=DEFAULT_SITEMAP_LIMIT)
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()
    if args.max_pages < 1 or args.sitemap_limit < 1 or args.timeout <= 0:
        parser.error("--max-pages, --sitemap-limit, and --timeout must be positive")
    return args


if __name__ == "__main__":
    raise SystemExit(asyncio.run(measure(parse_args())))
