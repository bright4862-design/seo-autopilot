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
from urllib.parse import urlsplit

REVISION = re.compile(r"fixlist-standard150-worker-[0-9]{5}-[a-z0-9]{3}\Z")


class CandidateNotIsolated(ValueError):
    """Not an exact, zero-traffic, tagged candidate."""


def verify_tagged_zero_traffic(
    service: dict, revision: str, tag: str = "candidate", *, source_sha: str = ""
) -> str:
    if not REVISION.fullmatch(revision):
        raise CandidateNotIsolated("revision_not_exact")
    if source_sha:
        if not re.fullmatch(r"[0-9a-f]{40}", source_sha) or tag != f"staged-{source_sha[:12]}":
            raise CandidateNotIsolated("source_tag_mismatch")
    elif tag != "candidate" and tag != f"canary-{revision.removeprefix('fixlist-standard150-worker-')}":
        raise CandidateNotIsolated("canary_tag_revision_mismatch")
    if not isinstance(service, dict):
        raise CandidateNotIsolated("service_not_object")
    status = service.get("status")
    if not isinstance(status, dict):
        raise CandidateNotIsolated("service_status_missing")
    traffic = status.get("traffic")
    if not isinstance(traffic, list) or not traffic:
        raise CandidateNotIsolated("service_traffic_missing")
    if tag != "candidate" and any(isinstance(entry, dict) and entry.get("tag") == tag
                                  and entry.get("revisionName") != revision for entry in traffic):
        raise CandidateNotIsolated("canary_tag_reassigned")
    candidates = [entry for entry in traffic
                  if isinstance(entry, dict) and entry.get("revisionName") == revision]
    if not candidates:
        raise CandidateNotIsolated("candidate_not_addressable")
    urls: set[str] = set()
    for entry in candidates:
        percent = entry.get("percent", 0)
        if type(percent) is not int or not 0 <= percent <= 100:
            raise CandidateNotIsolated("candidate_percent_invalid")
        if percent != 0:
            raise CandidateNotIsolated("candidate_receives_traffic")
        if entry.get("tag") == tag:
            url = entry.get("url")
            if not isinstance(url, str) or not url.startswith("https://"):
                raise CandidateNotIsolated("candidate_tag_url_missing")
            if tag != "candidate":
                origin = urlsplit(str(status.get("url") or ""))
                if (origin.scheme != "https" or not origin.hostname
                        or url.rstrip("/") != f"https://{tag}---{origin.hostname}"):
                    raise CandidateNotIsolated("canary_tag_url_mismatch")
            urls.add(url.rstrip("/"))
    if len(urls) != 1:
        raise CandidateNotIsolated("candidate_tag_missing_or_ambiguous")
    return next(iter(urls))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--tag", default="candidate")
    parser.add_argument("--source-sha", default="")
    args = parser.parse_args()
    try:
        service = json.load(sys.stdin)
        url = verify_tagged_zero_traffic(service, args.revision, args.tag, source_sha=args.source_sha)
    except (OSError, json.JSONDecodeError, CandidateNotIsolated) as exc:
        print(f"STAGED_WORKER_PROBE_BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(f"TAGGED_ZERO_TRAFFIC_CANDIDATE_OK revision={args.revision} tag_url={url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
