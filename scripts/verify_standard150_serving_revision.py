#!/usr/bin/env python3
"""Fail-closed, read-only Cloud Run control-plane check for the 100%-serving worker.

This is necessary but not runtime attestation: the private /revision response,
Base44 package parity, customer read-back and rollback remain separate gates.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


class ServingRevisionError(ValueError):
    pass


def generation(obj: dict, *path: str) -> int:
    value = obj
    for part in path:
        if not isinstance(value, dict):
            raise ServingRevisionError("cloud_run_generation_missing")
        value = value.get(part)
    if type(value) is not int or value < 1:
        raise ServingRevisionError("cloud_run_generation_missing")
    return value


def ready(obj: dict, role: str) -> None:
    if generation(obj, "metadata", "generation") != generation(obj, "status", "observedGeneration"):
        raise ServingRevisionError(f"{role}_generation_unreconciled")
    conditions = (obj.get("status") or {}).get("conditions")
    if (not isinstance(conditions, list)
            or sum(isinstance(c, dict) and c.get("type") == "Ready" and c.get("status") == "True"
                   for c in conditions) != 1
            or any(isinstance(c, dict) and c.get("type") == "Ready" and c.get("status") != "True"
                   for c in conditions)):
        raise ServingRevisionError(f"{role}_not_ready")


def select_serving_revision(service: dict) -> str:
    if not isinstance(service, dict):
        raise ServingRevisionError("invalid_service_json")
    ready(service, "service")
    traffic = (service.get("status") or {}).get("traffic")
    if not isinstance(traffic, list) or not traffic:
        raise ServingRevisionError("serving_traffic_unavailable")
    serving = []
    total = 0
    for item in traffic:
        if not isinstance(item, dict):
            raise ServingRevisionError("serving_traffic_invalid")
        percent = item.get("percent", 0)
        if type(percent) is not int or percent < 0 or percent > 100:
            raise ServingRevisionError("serving_traffic_invalid")
        total += percent
        if percent == 100:
            if item.get("tag"):
                raise ServingRevisionError("serving_traffic_tagged")
            serving.append(item.get("revisionName"))
    if (total != 100 or len(serving) != 1 or not isinstance(serving[0], str)
            or not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", serving[0])):
        raise ServingRevisionError("serving_revision_ambiguous")
    return serving[0]


def verify_revision_ready(revision: dict, selected: str, service_name: str) -> None:
    if not isinstance(revision, dict) or (revision.get("metadata") or {}).get("name") != selected:
        raise ServingRevisionError("selected_revision_identity_mismatch")
    ready(revision, "selected_revision")
    labels = (revision.get("metadata") or {}).get("labels") or {}
    if not isinstance(labels, dict) or labels.get("serving.knative.dev/service") != service_name:
        raise ServingRevisionError("selected_revision_service_mismatch")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service-json", type=Path, required=True)
    parser.add_argument("--revision-json", type=Path)
    args = parser.parse_args()
    try:
        service = json.loads(args.service_json.read_text("utf-8"))
        selected = select_serving_revision(service)
        if args.revision_json:
            revision = json.loads(args.revision_json.read_text("utf-8"))
            name = (service.get("metadata") or {}).get("name")
            if not isinstance(name, str) or not name:
                raise ServingRevisionError("service_identity_missing")
            verify_revision_ready(revision, selected, name)
    except (ServingRevisionError, OSError, ValueError, UnicodeError) as exc:
        print(f"SERVING_WORKER_PROOF_BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(selected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
