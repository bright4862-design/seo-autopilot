"""Named synthetic HTML through real extraction, scanning and local review.

Only DNS and HTTP transport are replaced. This corpus neither observes current
sites nor establishes the separate 30-site baseline/candidate acceptance gate.
Run directly with --output to create the input to scripts/assertCorpusRun.mjs.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import redirect_stdout
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scanner-api"))

from app import scanner  # noqa: E402
from app.beta_revision import live_revision  # noqa: E402
from app.canonical_validation import validate_canonical_targets  # noqa: E402
from app.extract import extract_page  # noqa: E402
from app.robots_policy import RobotsPolicy  # noqa: E402
from app.scan_job import build_local_review  # noqa: E402
from conftest import install_mock_network  # noqa: E402

MANIFEST_PATH = ROOT / "tests/fixtures/stage1-blueprint-corpus.json"
MANIFEST = json.loads(MANIFEST_PATH.read_text())
CASES = MANIFEST["cases"]


def _source_context() -> dict:
    files = sorted((ROOT / "scanner-api/app").glob("*.py")) + [
        Path(__file__), ROOT / "scripts/assertCorpusRun.mjs", MANIFEST_PATH,
    ]
    digest = sha256()
    for file in files:
        digest.update(str(file.relative_to(ROOT)).encode() + b"\0" + file.read_bytes() + b"\0")
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()
    return {
        "git_sha": revision, "source_tree_sha256": digest.hexdigest(),
        "execution": "actual_python_scanner_and_local_review",
        "fixture_transport": "httpx.MockTransport_and_public_DNS_snapshot",
        "versions": live_revision(),
    }


def _forbid_socket(*_args, **_kwargs):
    raise AssertionError("Synthetic corpus attempted a real outbound socket")


async def _observe_case(case: dict) -> dict:
    origin = case["origin"]
    routes = {
        origin + "/robots.txt": {"body": "User-agent: *\nAllow: /", "content_type": "text/plain"},
        origin + "/sitemap.xml": {"body": "<urlset></urlset>", "content_type": "application/xml"},
    }
    for item in case["pages"]:
        routes[origin + item["path"]] = {
            "body": item["html"], "status": item.get("status_code", 200),
            "headers": item.get("response_headers", {}),
        }
    for path, response in case.get("routes", {}).items():
        routes[origin + path] = response
    if case.get("sitemap_paths"):
        locations = "".join(f"<url><loc>{origin}{path}</loc></url>" for path in case["sitemap_paths"])
        routes[origin + "/sitemap.xml"]["body"] = "<urlset>" + locations + "</urlset>"

    with pytest.MonkeyPatch.context() as patch:
        requests = install_mock_network(patch, routes)
        patch.setattr(socket.socket, "connect", _forbid_socket)
        patch.setattr(socket, "create_connection", _forbid_socket)
        if case["mode"] == "run_scan":
            scan = await scanner.run_scan(origin + "/", scan_mode="basic", concurrency=1)
        else:
            pages = []
            for item in case["pages"]:
                url = origin + item["path"]
                discovery = {
                    "discovered_from": item.get("discovered_from", ["seed"]),
                    "source_pages": [origin + "/sitemap.xml"] if "sitemap" in item.get("discovered_from", []) else [],
                    "link_text_samples": [],
                }
                pages.append(extract_page(
                    item["html"], url, url, item.get("status_code", 200), "text/html", discovery,
                    response_headers=item.get("response_headers"),
                    body_truncated=item.get("body_truncated", False),
                ))
            async with httpx.AsyncClient() as client:
                await validate_canonical_targets(
                    client, pages, RobotsPolicy(origin + "/robots.txt", "missing", 404),
                )
            findings = scanner.build_findings(pages)
            scan = {
                "website_url": origin + "/", "normalized_url": origin + "/",
                "pages": pages, "crawled_pages": pages,
                "pages_crawled": len(pages), "pages_found": len(pages),
                "findings": findings, "grouped_findings": scanner.group_findings(findings),
                "scan_coverage": {"pages_found": len(pages), "pages_crawled": len(pages),
                                  "sampled_pages_sent_to_ai": len(pages)},
                "fixture_scope": "explicit synthetic accepted-response set; no live inventory claim",
            }
        review = build_local_review(scan)
        requested_urls = [
            f"{request.url.scheme}://{request.headers.get('host', '')}{request.url.raw_path.decode('ascii')}"
            for request in requests
        ]
    return {
        "id": case["id"], "site": case["site"], "origin": origin,
        "provenance": "synthetic", "mode": case["mode"],
        "scan": scan, "review": review, "requested_urls": requested_urls,
    }


def observe_corpus() -> dict:
    source = _source_context()
    # Real scanner emits structured progress logs; retain only the report in
    # the export stream so its JSON is directly consumable by the validator.
    with redirect_stdout(io.StringIO()):
        observed = [asyncio.run(_observe_case(case)) for case in CASES]
    final_source = _source_context()
    if source["source_tree_sha256"] != final_source["source_tree_sha256"]:
        raise RuntimeError("Scanner source changed during corpus execution; rerun against one source")
    return {
        "version": MANIFEST["version"], "provenance": "synthetic",
        "scope": MANIFEST["scope"], "full_30_site_gate": "not_assessed",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manifest_sha256": sha256(MANIFEST_PATH.read_bytes()).hexdigest(),
        "source": source, "cases": observed,
    }


@pytest.fixture(scope="module")
def corpus_report(tmp_path_factory):
    report = observe_corpus()
    path = Path(os.environ.get("FIXLIST_STAGE1_CORPUS_OUTPUT") or tmp_path_factory.mktemp("stage1-corpus") / "observed.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")
    return report, path


def test_actual_named_corpus_observations_satisfy_blueprint_assertions(corpus_report):
    report, path = corpus_report
    assert len(report["cases"]) == len(CASES)
    node = os.environ.get("FIXLIST_CORPUS_NODE") or shutil.which("node")
    assert node, "Node is required to run the shared corpus acceptance validator"
    result = subprocess.run(
        [node, "scripts/assertCorpusRun.mjs", str(path)], cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_corpus_uses_exact_named_hosts_and_synthetic_provenance(corpus_report):
    report, _ = corpus_report
    assert {case["origin"] for case in report["cases"]} == {
        "https://pretto.fr", "https://centerstreetlending.com", "https://www.ikessandwich.com",
        "https://locations.ikessandwich.com", "https://getfixlist.com", "https://ironwoodcrecapital.com",
    }
    assert all(case["provenance"] == "synthetic" for case in report["cases"])
    assert report["full_30_site_gate"] == "not_assessed"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    observed = observe_corpus()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(observed, indent=2) + "\n")
