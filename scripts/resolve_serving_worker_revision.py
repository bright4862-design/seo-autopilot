#!/usr/bin/env python3
"""Read-only, fail-closed Cloud Run v1 status.traffic 100%-serving revision selector.

This identifies a requested route-verification target, not the process that
answered an authenticated HTTP request. Runtime /revision must still be checked.
"""
from __future__ import annotations

import json
import re
import sys


class ServingRevisionUnavailable(ValueError):
    pass


def resolve(service: dict, *, service_name: str) -> str:
    if not isinstance(service, dict):
        raise ServingRevisionUnavailable("service_not_object")
    metadata = service.get("metadata") or {}
    status = service.get("status") or {}
    if not isinstance(metadata, dict) or not isinstance(status, dict):
        raise ServingRevisionUnavailable("service_metadata_or_status_invalid")
    generation = metadata.get("generation")
    observed = status.get("observedGeneration")
    if generation is None or observed is None or str(generation) != str(observed):
        raise ServingRevisionUnavailable("service_reconciliation_not_observed")
    conditions = status.get("conditions") or []
    if not isinstance(conditions, list):
        raise ServingRevisionUnavailable("service_conditions_invalid")
    ready = [item for item in conditions if isinstance(item, dict) and item.get("type") == "Ready"]
    if len(ready) != 1 or str(ready[0].get("status") or "").lower() != "true":
        raise ServingRevisionUnavailable("service_not_ready")
    traffic = status.get("traffic")
    if not isinstance(traffic, list) or not traffic:
        raise ServingRevisionUnavailable("service_traffic_missing")
    active = []
    for row in traffic:
        if not isinstance(row, dict):
            raise ServingRevisionUnavailable("service_traffic_invalid")
        percent = row.get("percent", 0)
        if isinstance(percent, bool) or not isinstance(percent, int) or not 0 <= percent <= 100:
            raise ServingRevisionUnavailable("service_traffic_percent_invalid")
        if percent:
            active.append((percent, row.get("revisionName")))
    if len(active) != 1 or active[0][0] != 100:
        raise ServingRevisionUnavailable("service_not_single_100_percent_revision")
    revision = active[0][1]
    if not isinstance(revision, str) or not re.fullmatch(re.escape(service_name) + r"-[0-9]{5}-[a-z0-9]{3}", revision):
        raise ServingRevisionUnavailable("service_serving_revision_invalid")
    return revision


def main() -> int:
    if len(sys.argv) != 2 or not re.fullmatch(r"[a-z][a-z0-9-]{1,62}", sys.argv[1]):
        print("INDETERMINATE: expected exact Cloud Run service name argument", file=sys.stderr)
        return 2
    try:
        value = json.load(sys.stdin)
        selected = resolve(value, service_name=sys.argv[1])
    except (ServingRevisionUnavailable, ValueError, TypeError) as exc:
        print(f"INDETERMINATE: {exc}", file=sys.stderr)
        return 2
    print(selected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
