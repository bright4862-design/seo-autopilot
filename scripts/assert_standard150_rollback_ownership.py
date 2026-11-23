#!/usr/bin/env python3
"""Read-only best-effort ownership guard before restoring Standard 150 traffic.

This is not an atomic Cloud Run conditional update. A concurrent mutation can
still race between this snapshot and an eventual update-traffic command.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def positive_allocations(value: object, label: str) -> dict[str, int]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} traffic missing")
    seen: set[str] = set()
    positive: dict[str, int] = {}
    for item in value:
        if not isinstance(item, dict) or item.get("latestRevision") or item.get("configurationName"):
            raise ValueError(f"{label} contains floating or malformed traffic")
        revision = item.get("revisionName")
        percent = item.get("percent", 0)
        if not isinstance(revision, str) or not revision or revision in seen:
            raise ValueError(f"{label} has unnamed or duplicate revision")
        if type(percent) is not int or not (0 <= percent <= 100):
            raise ValueError(f"{label} has invalid percent")
        seen.add(revision)
        if percent:
            positive[revision] = percent
    if sum(positive.values()) != 100:
        raise ValueError(f"{label} does not total 100 percent")
    return positive


def check_ownership(service: object, candidate: str, prior: str) -> str:
    if not candidate or not prior or candidate == prior:
        raise ValueError("invalid candidate/prior revision")
    if not isinstance(service, dict) or not isinstance(service.get("spec"), dict) or not isinstance(service.get("status"), dict):
        raise ValueError("service spec/status unavailable")
    desired = positive_allocations(service["spec"].get("traffic"), "desired")
    observed = positive_allocations(service["status"].get("traffic"), "observed")
    accepted = {candidate, prior}
    if set(desired) - accepted or set(observed) - accepted:
        raise ValueError("foreign revision owns positive desired or observed traffic")
    if desired == observed == {prior: 100}:
        return "ALREADY_RESTORED"
    if candidate in desired or candidate in observed:
        return "ALLOW_RESTORE"
    raise ValueError("traffic ownership is indeterminate")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service-json", type=Path, required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--prior", required=True)
    args = parser.parse_args()
    try:
        snapshot = json.loads(args.service_json.read_text(encoding="utf-8"))
        outcome = check_ownership(snapshot, args.candidate, args.prior)
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(2, f"ROLLBACK_CONFLICT: {exc}\n")
    print(outcome)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
