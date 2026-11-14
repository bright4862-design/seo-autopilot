#!/usr/bin/env python3
"""Read-only guard for the Cloud Run service's *stable* 100%-serving revision.

This is not a deployment/rollback authorization. It refuses a misleading
/revision PASS while desired traffic is moving away from the observed worker.
Use before and after an authenticated probe; the second read catches changes
that happened during the probe, but cannot prevent later concurrent changes.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


class TopologyError(ValueError):
    pass


def positive_int(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise TopologyError(f"{label}: boolean generation")
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and re.fullmatch(r"[1-9][0-9]*", value):
        return int(value)
    raise TopologyError(f"{label}: positive generation required")


def traffic(rows: object, label: str) -> tuple[str, tuple[str, ...]]:
    if not isinstance(rows, list) or not rows:
        raise TopologyError(f"{label}: traffic inventory missing")
    positive = []
    normalized = []
    for item in rows:
        if not isinstance(item, dict):
            raise TopologyError(f"{label}: non-object traffic entry")
        if item.get("latestRevision") is True or item.get("latestConfiguration") is True:
            raise TopologyError(f"{label}: floating latest traffic not allowed")
        pct = item.get("percent", 0)
        if isinstance(pct, bool) or not isinstance(pct, int) or not 0 <= pct <= 100:
            raise TopologyError(f"{label}: invalid percentage")
        revision = item.get("revisionName")
        if not isinstance(revision, str) or not revision.strip():
            raise TopologyError(f"{label}: explicit pinned revision required")
        if pct > 0:
            positive.append((revision, pct))
        normalized.append(json.dumps(item, sort_keys=True, separators=(",", ":")))
    if len(positive) != 1 or positive[0][1] != 100:
        raise TopologyError(f"{label}: exactly one pinned 100% allocation required")
    return positive[0][0], tuple(sorted(normalized))


def snapshot(service: object, expected_service: str) -> tuple[object, ...]:
    if not isinstance(service, dict):
        raise TopologyError("service: JSON object required")
    metadata = service.get("metadata")
    status = service.get("status")
    spec = service.get("spec")
    if not isinstance(metadata, dict) or not isinstance(status, dict) or not isinstance(spec, dict):
        raise TopologyError("service: metadata/spec/status must be objects")
    if metadata.get("name") != expected_service:
        raise TopologyError("service: unexpected Cloud Run service name")
    generation = positive_int(metadata.get("generation"), "metadata.generation")
    observed = positive_int(status.get("observedGeneration"), "status.observedGeneration")
    if observed != generation:
        raise TopologyError("service: desired generation is still reconciling")
    conditions = status.get("conditions")
    ready = [c for c in conditions if isinstance(c, dict) and c.get("type") == "Ready"] if isinstance(conditions, list) else []
    if len(ready) != 1 or ready[0].get("status") != "True":
        raise TopologyError("service: Ready condition not True")
    desired_rev, desired_rows = traffic(spec.get("traffic"), "spec.traffic")
    observed_rev, observed_rows = traffic(status.get("traffic"), "status.traffic")
    if desired_rev != observed_rev:
        raise TopologyError("service: desired and observed serving revisions differ")
    return (generation, desired_rev, desired_rows, observed_rows)


def load(path: str) -> object:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TopologyError(f"unreadable service inventory: {exc.__class__.__name__}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service_json", help="Independent gcloud run services describe JSON")
    parser.add_argument("--service", required=True, help="Exact expected Cloud Run service")
    parser.add_argument("--baseline", help="First independent service inventory, before /revision")
    parser.add_argument("--expect-revision", help="Exact 100%-serving revision selected earlier")
    args = parser.parse_args()
    try:
        current = snapshot(load(args.service_json), args.service)
        if args.expect_revision and current[1] != args.expect_revision:
            raise TopologyError("service: selected serving revision changed")
        if args.baseline and current != snapshot(load(args.baseline), args.service):
            raise TopologyError("service: serving topology changed during /revision probe")
    except TopologyError as exc:
        print(f"INDETERMINATE: {exc}", file=sys.stderr)
        return 2
    print(current[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
