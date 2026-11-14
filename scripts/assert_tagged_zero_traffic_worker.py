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


def verify_tagged_zero_traffic(service: dict, revision: str, tag: str = "candidate") -> str:
    if not REVISION.fullmatch(revision):
        raise CandidateNotIsolated("revision_not_exact")
    if tag != "candidate" and tag != f"canary-{revision.removeprefix('fixlist-standard150-worker-')}":
        raise CandidateNotIsolated("canary_tag_revision_mismatch")
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
    origin = urlsplit(str(status.get("url") or ""))
    if (origin.scheme != "https" or not origin.hostname
            or not origin.hostname.endswith(".run.app")
            or origin.netloc != origin.hostname or origin.path
            or origin.query or origin.fragment):
        raise CandidateNotIsolated("service_origin_invalid")
    expected_url = f"https://{tag}---{origin.hostname}"
    tagged_urls: list[str] = []
    for entry in candidates:
        try:
            percent = int(entry.get("percent") or 0)
        except (ValueError, TypeError) as exc:
            raise CandidateNotIsolated("candidate_percent_invalid") from exc
        if percent != 0:
            raise CandidateNotIsolated("candidate_receives_traffic")
        if entry.get("tag") == tag:
            url = entry.get("url")
            if not isinstance(url, str) or not url.startswith("https://"):
                raise CandidateNotIsolated("candidate_tag_url_missing")
            # A Cloud Run tag stays on the canonical service hostname. Merely
            # starting with HTTPS is not enough: an unrelated HTTPS endpoint
            # must never become the destination of an authenticated probe.
            if url != expected_url:
                raise CandidateNotIsolated("candidate_tag_url_mismatch" if tag == "candidate"
                                           else "canary_tag_url_mismatch")
            tagged_urls.append(url)
    # Report the requested revision's own errors first (not addressable,
    # serving traffic) before diagnosing a conflicting shared tag assignment.
    if any(isinstance(entry, dict) and entry.get("tag") == tag
           and entry.get("revisionName") != revision for entry in traffic):
        raise CandidateNotIsolated("candidate_tag_reassigned" if tag == "candidate"
                                   else "canary_tag_reassigned")
    if len(tagged_urls) != 1:
        raise CandidateNotIsolated("candidate_tag_missing_or_ambiguous")
    return tagged_urls[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--tag", default="candidate")
    args = parser.parse_args()
    try:
        service = json.load(sys.stdin)
        url = verify_tagged_zero_traffic(service, args.revision, args.tag)
    except (OSError, json.JSONDecodeError, CandidateNotIsolated) as exc:
        print(f"STAGED_WORKER_PROBE_BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(f"TAGGED_ZERO_TRAFFIC_CANDIDATE_OK revision={args.revision} tag_url={url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
