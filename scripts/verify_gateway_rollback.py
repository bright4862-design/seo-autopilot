#!/usr/bin/env python3
"""Verify rollback against the previous serving revision, not the new template."""
import argparse
import json
import re
import sys
from verify_gateway_deployment import VerificationError, verify_created_revision, verify_runtime_health


def verify(service, revision, health, baseline, expected_revision, source_sha):
    if not all(isinstance(doc, dict) for doc in (service, revision, health, baseline)):
        raise VerificationError("Rollback evidence must be JSON objects")
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise VerificationError("Rollback source SHA is missing")
    verify_created_revision(revision, expected_revision, source_sha)
    traffic = service.get("status", {}).get("traffic", [])
    if sum(int(t.get("percent") or 0) for t in traffic if t.get("revisionName") == expected_revision) != 100:
        raise VerificationError("Previous gateway does not hold 100% traffic")
    if "@sha256:" not in str(revision.get("status", {}).get("imageDigest") or ""):
        raise VerificationError("Previous gateway has no immutable image digest")
    # spec.template can still name the failed new deployment after rollback.
    # Readiness, source and runtime identity belong to the previous revision.
    if baseline.get("revision") != expected_revision or baseline.get("source_sha") != source_sha:
        raise VerificationError("Rollback baseline identity is not the previous revision")
    for key in ("contract_version", "queue", "drain_queue", "worker_origin"):
        if not baseline.get(key):
            raise VerificationError(f"Rollback baseline missing {key}")
    canary = {}
    if "canary_worker_origin" in baseline:
        canary = {"canary_worker_origin": baseline["canary_worker_origin"] or "",
                  "canary_owner_count": baseline.get("canary_owner_count", 0)}
    verify_runtime_health(health, expected_revision, source_sha, baseline["contract_version"],
                          baseline["queue"], baseline["drain_queue"], baseline["worker_origin"], **canary)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("service-json", "revision-json", "health-json", "baseline-json", "expected-revision", "expected-source-sha"):
        p.add_argument("--"+name, required=True)
    a = p.parse_args()
    def load(path):
        with open(path) as f: return json.load(f)
    try:
        verify(load(a.service_json), load(a.revision_json), load(a.health_json), load(a.baseline_json),
               a.expected_revision, a.expected_source_sha)
    except (VerificationError, ValueError, OSError, KeyError, TypeError) as exc:
        print(f"GATEWAY_ROLLBACK_FAILED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
