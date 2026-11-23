#!/usr/bin/env python3
"""Read-only Cloud Run revision routing check. Never output environment or secret values."""
from __future__ import annotations

import argparse
import json
import sys

EXPECTED_APP_ID = "6a498732ec779dfaaeab0e53"
EXPECTED_ORIGIN = "https://base44.app"


class RoutingProofError(ValueError):
    pass


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RoutingProofError("duplicate JSON member")
        result[key] = value
    return result


def verify_revision_binding(document: object, revision: str) -> None:
    """Fail closed unless this exact Ready revision routes to the pinned Base44 app."""
    if (not isinstance(document, dict) or not revision
            or not isinstance(document.get("metadata"), dict)
            or document["metadata"].get("name") != revision):
        raise RoutingProofError("revision identity unavailable or mismatched")
    spec = document.get("spec")
    containers = spec.get("containers") if isinstance(spec, dict) else None
    if not isinstance(containers, list) or len(containers) != 1 or not isinstance(containers[0], dict):
        raise RoutingProofError("exactly one revision container required")
    items = containers[0].get("env")
    if not isinstance(items, list):
        raise RoutingProofError("revision environment unavailable")
    environment = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise RoutingProofError("malformed revision environment")
        name = item["name"]
        if name in environment:
            raise RoutingProofError("duplicate revision environment name")
        environment[name] = item
    for key, expected in (("BASE44_APP_ID", EXPECTED_APP_ID), ("BASE44_API_URL", EXPECTED_ORIGIN)):
        item = environment.get(key)
        if item is None or item.get("value") != expected or "valueFrom" in item:
            raise RoutingProofError(f"{key} does not match the pinned Standard 150 route")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args(argv)
    try:
        raw = sys.stdin.buffer.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise RoutingProofError("revision metadata exceeds read limit")
        parsed = json.loads(raw, object_pairs_hook=_unique_object)
        verify_revision_binding(parsed, args.revision)
    except (ValueError, TypeError, AttributeError) as exc:
        # No environment values or secret references are printed here.
        print(f"WORKER_BASE44_ROUTE_UNVERIFIED: {exc}", file=sys.stderr)
        return 1
    print("WORKER_BASE44_ROUTE_MATCH")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
