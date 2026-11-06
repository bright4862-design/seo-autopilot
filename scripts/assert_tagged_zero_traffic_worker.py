#!/usr/bin/env python3
"""Verify a Cloud Run worker revision is tagged, addressable and receives 0%.

Read-only preflight for the private candidate /revision probe. Never infer a
candidate from latestReadyRevisionName or from the canonical service URL.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

REVISION = re.compile(r"fixlist-standard150-worker-[0-9]{5}-[a-z0-9]{3}\Z")


class CandidateNotIsolated(ValueError):
    """Not an exact, zero-traffic, tagged candidate."""


def verify_tagged_zero_traffic(service: dict, revision: str) -> str:
    if not REVISION.fullmatch(revision):
        raise CandidateNotIsolated("revision_not_exact")
    if not isinstance(service, dict):
        raise CandidateNotIsolated("service_not_object")
    status = service.get("status")
    if not isinstance(status, dict):
        raise CandidateNotIsolated("service_status_missing")
    traffic = status.get("traffic")
    if not isinstance(traffic, list) or not traffic:
        raise CandidateNotIsolated("service_traffic_missing")
    candidates = [entry for entry in traffic
                  if isinstance(entry, dict) and entry.get("revisionName") == revision]
    if not candidates:
        raise CandidateNotIsolated("candidate_not_addressable")
    urls: set[str] = set()
    for entry in candidates:
        try:
            percent = int(entry.get("percent") or 0)
        except (ValueError, TypeError) as exc:
            raise CandidateNotIsolated("candidate_percent_invalid") from exc
        if percent != 0:
            raise CandidateNotIsolated("candidate_receives_traffic")
        if entry.get("tag") == "candidate":
            url = entry.get("url")
            if not isinstance(url, str) or not url.startswith("https://"):
                raise CandidateNotIsolated("candidate_tag_url_missing")
            urls.add(url.rstrip("/"))
    if len(urls) != 1:
        raise CandidateNotIsolated("candidate_tag_missing_or_ambiguous")
    return next(iter(urls))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    try:
        service = json.load(sys.stdin)
        url = verify_tagged_zero_traffic(service, args.revision)
    except (OSError, json.JSONDecodeError, CandidateNotIsolated) as exc:
        print(f"STAGED_WORKER_PROBE_BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(f"TAGGED_ZERO_TRAFFIC_CANDIDATE_OK revision={args.revision} tag_url={url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
