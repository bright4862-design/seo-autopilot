#!/usr/bin/env python3
"""Fail closed unless Cloud Run independently shows the rollback revision at 100%.

Read-only post-mutation assertion. This is NOT Standard 150 product acceptance,
a customer canary, or protection against subsequent concurrent traffic edits.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _generation(value: object) -> int:
    if type(value) is int and value > 0:
        return value
    if isinstance(value, str) and value.isascii() and value.isdecimal() and int(value) > 0:
        return int(value)
    raise ValueError("missing or invalid service generation")


def _expect_100(traffic: object, expected: str, source: str) -> None:
    if not isinstance(traffic, list) or not traffic:
        raise ValueError(f"{source} traffic missing")
    positive = []
    for item in traffic:
        if not isinstance(item, dict) or item.get("latestRevision") or item.get("configurationName"):
            raise ValueError(f"{source} traffic contains floating or malformed allocation")
        revision = item.get("revisionName")
        percent = item.get("percent", 0)
        if not isinstance(revision, str) or not revision:
            raise ValueError(f"{source} traffic has unnamed allocation")
        if type(percent) is not int or not 0 <= percent <= 100:
            raise ValueError(f"{source} traffic has invalid percentage")
        if percent:
            positive.append((revision, percent))
    if positive != [(expected, 100)]:
        raise ValueError(f"{source} traffic is not exactly {expected}=100")


def check_readback(service: object, expected: str) -> None:
    if not isinstance(service, dict) or not isinstance(expected, str) or not expected:
        raise ValueError("invalid service or revision identity")
    metadata, status, spec = service.get("metadata"), service.get("status"), service.get("spec")
    if not all(isinstance(x, dict) for x in (metadata, status, spec)):
        raise ValueError("incomplete Cloud Run service state")
    generation = _generation(metadata.get("generation"))
    observed = _generation(status.get("observedGeneration"))
    if generation != observed:
        raise ValueError("rollback not reconciled: observed generation differs")
    conditions = status.get("conditions")
    if not isinstance(conditions, list) or not any(
        isinstance(c, dict) and c.get("type") == "Ready" and c.get("status") == "True"
        for c in conditions
    ):
        raise ValueError("rollback service is not Ready")
    _expect_100(spec.get("traffic"), expected, "desired")
    _expect_100(status.get("traffic"), expected, "observed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-revision", required=True)
    parser.add_argument("--service-json", type=Path, required=True)
    args = parser.parse_args()
    try:
        service = json.loads(args.service_json.read_text(encoding="utf-8"))
        check_readback(service, args.expected_revision)
    except (ValueError, OSError, TypeError) as exc:
        parser.exit(2, f"ROLLBACK_UNVERIFIED: {exc}\n")
    print(f"ROLLBACK_TRAFFIC_READBACK_OK revision={args.expected_revision}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
