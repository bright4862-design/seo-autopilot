#!/usr/bin/env python3
"""Replay reviewed captures against exact Git selectors, without network access.

Inputs are the corpus manifest and a private staged_scan_selection_captures_v1
JSON file. Each capture's captured_at is the UTC time of initial selection, not
the download time. Keep sitemap_urls and homepage_links in captured order.
The report measures selection in the captured sitemap inventory, not whether
the selected pages were fetched or a live scan reached a verified terminal state.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from importlib import import_module, util
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
from urllib.parse import urlparse, urlsplit


ROOT = Path(__file__).resolve().parents[2]
BASELINE_SHA = "689a7fb43825f322af70188e7426730552daebd9"
BASELINE_VERSION = "balanced_sitemap_buckets_v7_commercial_hubs_before_repeated_leaves"
REFERENCE_HOSTS = {
    "funbooker": "funbooker.com",
    "pretto": "pretto.fr",
    "center_street_lending": "centerstreetlending.com",
    "norris_wines": "norriswines.com",
}
CAPTURE_FIELDS = {
    "site_id", "start_url", "captured_at", "sitemap_urls", "homepage_links",
    "sitemap_lastmod", "preferred_market", "inventory_capped",
}


class ComparisonError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise ComparisonError(code)


def matches(pattern, value):
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def sha256(value):
    return hashlib.sha256(value).hexdigest()


def canonical_json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("ascii")


def unique_object(pairs):
    result = dict(pairs)
    require(len(result) == len(pairs), "duplicate_json_key")
    return result


def read_document(path, byte_limit):
    require(path.is_absolute() and path.parent.resolve() == path.parent, "input_path_invalid")
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    with os.fdopen(os.open(path, flags), "rb") as source:
        info = os.fstat(source.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_size <= byte_limit, "input_file_invalid")
        data = source.read(byte_limit + 1)
    require(len(data) <= byte_limit, "input_file_invalid")
    return json.loads(data, object_pairs_hook=unique_object), sha256(data)


def git(*args):
    return subprocess.check_output(
        ["git", "--no-replace-objects", *args], cwd=ROOT, stderr=subprocess.DEVNULL,
        env={**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_TERMINAL_PROMPT": "0"},
    )


@contextmanager
def pinned_package(source_sha, namespace):
    require(git("rev-parse", "--verify", f"{source_sha}^{{commit}}").decode().strip() == source_sha,
            "selector_revision_unverified")
    source = git("archive", "--format=tar", source_sha, "scanner-api/app")
    with TemporaryDirectory(prefix="fixlist-selection-source-") as directory:
        with tarfile.open(fileobj=io.BytesIO(source), mode="r:") as archive:
            archive.extractall(directory, filter="data")
        package = Path(directory) / "scanner-api/app"
        spec = util.spec_from_file_location(namespace, package / "__init__.py", submodule_search_locations=[str(package)])
        module = util.module_from_spec(spec)
        sys.modules[namespace] = module
        try:
            spec.loader.exec_module(module)
            yield import_module(f"{namespace}.sampling"), import_module(f"{namespace}.extract").classify_template
        finally:
            for name in list(sys.modules):
                if name == namespace or name.startswith(f"{namespace}."):
                    del sys.modules[name]


def valid_url(url, *, allow_relative=False):
    require(isinstance(url, str) and len(url) <= 8192 and not re.search(r"[\x00-\x1f\x7f]", url), "capture_url_invalid")
    try:
        parts = urlsplit(url)
        if allow_relative and not parts.scheme and not parts.netloc and parts.path:
            return parts
        require(parts.scheme in {"http", "https"} and parts.hostname and parts.username is None
                and parts.password is None and "#" not in url, "capture_url_invalid")
        return parts
    except ValueError:
        raise ComparisonError("capture_url_invalid") from None


def site_host(url):
    return valid_url(url).hostname.removeprefix("www.").rstrip(".")


def manifest_sites(manifest):
    require(isinstance(manifest, dict) and manifest.get("schema_version") == "staged_scan_corpus_v1"
            and matches(r"[a-f0-9]{40}", manifest.get("source_sha"))
            and matches(r"[a-f0-9]{16}", manifest.get("release_fingerprint")), "corpus_manifest_invalid")
    sites = manifest.get("sites")
    require(isinstance(sites, list) and len(sites) == 50, "corpus_requires_50_sites")
    by_id, hosts, references = {}, set(), set()
    for row in sites:
        require(isinstance(row, dict) and matches(r"[A-Za-z0-9_-]{1,80}", row.get("site_id")), "corpus_site_invalid")
        site_id = row["site_id"]
        host = site_host(row.get("target_url"))
        require(site_id not in by_id and host not in hosts and "reference_marker" in row, "corpus_site_identity_invalid")
        marker = row["reference_marker"]
        if marker is not None:
            require(isinstance(marker, str) and REFERENCE_HOSTS.get(marker) == host, "corpus_reference_host_mismatch")
            references.add(marker)
        by_id[site_id] = row
        hosts.add(host)
    require(references == set(REFERENCE_HOSTS), "corpus_reference_missing")
    return by_id


def capture_sites(document, corpus, manifest_digest):
    require(isinstance(document, dict) and document.get("schema_version") == "staged_scan_selection_captures_v1"
            and set(document) == {"schema_version", "corpus_manifest_sha256", "sites"}, "capture_schema_invalid")
    require(document["corpus_manifest_sha256"] == manifest_digest, "captures_manifest_mismatch")
    rows = document["sites"]
    require(isinstance(rows, list) and len(rows) == len(corpus), "capture_inventory_mismatch")
    by_id = {}
    for row in rows:
        require(isinstance(row, dict) and set(row) - {"terminal_anchor"} == CAPTURE_FIELDS, "capture_schema_invalid")
        site_id = row["site_id"]
        require(isinstance(site_id, str) and site_id in corpus and site_id not in by_id, "capture_inventory_mismatch")
        require(site_host(row["start_url"]) == site_host(corpus[site_id]["target_url"]), "capture_target_mismatch")
        by_id[site_id] = row
    return by_id


def selection_input(capture):
    inventory, navigation = capture["sitemap_urls"], capture["homepage_links"]
    host = site_host(capture["start_url"])
    for urls, allow_relative in ((inventory, True), (navigation, False)):
        require(isinstance(urls, list) and len(urls) <= 5000, "capture_url_inventory_invalid")
        for url in urls:
            parts = valid_url(url, allow_relative=allow_relative)
            require(parts.hostname is None or parts.hostname.removeprefix("www.").rstrip(".") == host,
                    "capture_url_host_mismatch")
        require(len(set(urls)) == len(urls), "capture_url_inventory_invalid")
    require(bool(inventory), "capture_sitemap_inventory_missing")
    require(type(capture["inventory_capped"]) is bool and isinstance(capture["preferred_market"], str)
            and len(capture["preferred_market"]) <= 128, "capture_selection_metadata_invalid")
    ordered = list(dict.fromkeys(inventory + navigation))
    ordered = [url for url in ordered if url != capture["start_url"]]
    lastmod = capture["sitemap_lastmod"]
    require(isinstance(lastmod, dict) and lastmod.keys() <= set(inventory)
            and all(isinstance(value, str) and len(value) <= 128 for value in lastmod.values()), "capture_lastmod_invalid")
    try:
        selected_at = datetime.fromisoformat(capture["captured_at"])
        require(selected_at.utcoffset() is not None, "capture_time_invalid")
    except (ValueError, TypeError, OverflowError):
        raise ComparisonError("capture_time_invalid") from None
    return ordered, selected_at.astimezone(timezone.utc)


def terminal_anchor(capture):
    anchor = capture.get("terminal_anchor")
    if anchor is None:
        return None
    require(isinstance(anchor, dict) and set(anchor) == {"scan_id", "attempt_count", "frontier_generation", "receipt_snapshot_sha256"}
            and matches(r"[A-Za-z0-9_-]{6,160}", anchor["scan_id"])
            and type(anchor["attempt_count"]) is int and 0 < anchor["attempt_count"] < 2**31
            and matches(r"[1-9][0-9]{0,23}", anchor["frontier_generation"])
            and matches(r"[a-f0-9]{64}", anchor["receipt_snapshot_sha256"]), "capture_terminal_anchor_invalid")
    return anchor


def path_of(url):
    return urlparse(url).path or "/"


def compare_site(site, capture, baseline, baseline_family, candidate, candidate_family, build_importance):
    ordered, selected_at = selection_input(capture)
    anchor = terminal_anchor(capture)
    inventory = capture["sitemap_urls"]
    market = capture["preferred_market"]
    navigation = capture["homepage_links"]
    scores = build_importance(ordered, candidate_family, path_of, homepage_links=navigation,
                              lastmod=capture["sitemap_lastmod"], now=selected_at)
    # Both selectors see the same ordered input. The homepage is reserved as
    # in the worker and excluded from initial non-home selection diagnostics.
    selections = (
        baseline.select_balanced_urls(ordered, baseline_family, path_of, 149, preferred_market=market),
        candidate.select_balanced_urls(ordered, candidate_family, path_of, 149, preferred_market=market,
                                       homepage_links=navigation, importance_scores=scores),
        candidate.select_balanced_urls(ordered, candidate_family, path_of, 499, preferred_market=market,
                                       homepage_links=navigation, importance_scores=scores),
    )
    section_by_url = candidate.section_keys(inventory, path_of)
    discovered = Counter(section_by_url.values())
    baseline_counts, counts_150, counts_500 = (
        Counter(section_by_url[url] for url in selected if url in section_by_url) for selected in selections
    )
    rows = [{
        "section_sha256": sha256(section.encode("utf-8")), "discovered": count,
        "v7_selected_150": baseline_counts[section], "candidate_selected_150": counts_150[section],
        "candidate_selected_500": counts_500[section],
    } for section, count in discovered.items()]
    return {
        "site_id": site["site_id"], "reference_marker": site["reference_marker"],
        "capture_sha256": sha256(canonical_json(capture)), "claimed_terminal_anchor": anchor,
        "inventory_capped": capture["inventory_capped"], "inventory_urls": len(inventory),
        "candidate_selected_urls_500": len(selections[2]),
        "sections": sorted(rows, key=lambda row: row["section_sha256"]),
    }


def summarize(reports):
    sections = [section for row in reports for section in row["sections"]]
    references = [{
        "site_id": row["site_id"], "reference_marker": row["reference_marker"],
        "lost_v7_sections_at_150": sum(section["v7_selected_150"] > 0 and section["candidate_selected_150"] == 0
                                      for section in row["sections"]),
    } for row in reports if row["reference_marker"] is not None]
    summary = {
        "v7_150_sections_never_selected": sum(row["v7_selected_150"] == 0 for row in sections),
        "candidate_150_sections_never_selected": sum(row["candidate_selected_150"] == 0 for row in sections),
        "candidate_500_sections_never_selected": sum(row["candidate_selected_500"] == 0 for row in sections),
        "references": references,
    }
    passed = (summary["candidate_150_sections_never_selected"] < summary["v7_150_sections_never_selected"]
              and all(row["lost_v7_sections_at_150"] == 0 for row in references))
    return summary, passed


def build_report(manifest, manifest_digest, document, captures_digest):
    sites = manifest_sites(manifest)
    captures = capture_sites(document, sites, manifest_digest)
    source = manifest["source_sha"]
    released = json.loads(git("show", f"{source}:data/beta-crawler-revision.json"))
    require(released.get("fingerprint") == manifest["release_fingerprint"], "candidate_fingerprint_mismatch")
    git("merge-base", "--is-ancestor", BASELINE_SHA, source)
    with pinned_package(BASELINE_SHA, "fixlist_selection_v7") as (baseline, baseline_classify):
        require(baseline.SAMPLING_VERSION == BASELINE_VERSION, "baseline_sampler_mismatch")
        with pinned_package(source, "fixlist_selection_candidate") as (candidate, candidate_classify):
            require(candidate.SAMPLING_VERSION != BASELINE_VERSION and hasattr(candidate, "section_keys"), "candidate_sampler_invalid")
            importance = import_module("fixlist_selection_candidate.page_importance").build_page_importance
            reports = [compare_site(site, captures[site_id], baseline, lambda url: baseline_classify(path_of(url)),
                                    candidate, lambda url: candidate_classify(path_of(url)), importance)
                       for site_id, site in sites.items()]
    summary, passed = summarize(reports)
    return {
        "schema_version": "staged_scan_selection_comparison_v1",
        "evidence_scope": "offline_replay_of_captured_sitemap_selection",
        "baseline_source_sha": BASELINE_SHA, "baseline_sampling_version": BASELINE_VERSION,
        "candidate_source_sha": source, "candidate_sampling_version": candidate.SAMPLING_VERSION,
        "release_fingerprint": manifest["release_fingerprint"],
        "corpus_manifest_sha256": manifest_digest, "captures_sha256": captures_digest,
        "site_count": len(reports),
        "selection_comparison_verified": passed, "live_terminal_evidence_verified": False,
        "summary": summary, "sites": reports,
    }


def write_report(path, report):
    require(path.is_absolute() and path.parent.resolve() == path.parent, "output_path_invalid")
    require(not path.is_relative_to(ROOT), "output_must_be_outside_checkout")
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as output:
        output.write(canonical_json(report) + b"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path, help="absolute path to exact reviewed corpus manifest")
    parser.add_argument("--captures", required=True, type=Path, help="absolute path to private inventory captures")
    parser.add_argument("--output", required=True, type=Path, help="new absolute report path outside the checkout")
    args = parser.parse_args()
    try:
        manifest, manifest_digest = read_document(args.manifest, 1024**2)
        document, captures_digest = read_document(args.captures, 256 * 1024**2)
        report = build_report(manifest, manifest_digest, document, captures_digest)
        write_report(args.output, report)
    except ComparisonError as error:
        print(error, file=sys.stderr)
        return 2
    except (OSError, ValueError, subprocess.SubprocessError, ImportError, tarfile.TarError):
        print("selection_comparison_unavailable", file=sys.stderr)
        return 2
    return 0 if report["selection_comparison_verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
