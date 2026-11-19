#!/usr/bin/env python3
"""Read the serving Cloud Run worker's signing reference, never its secret value.

Metadata-only diagnostic. Does NOT prove HMAC validity, Base44 key alignment,
or successful persistence.
"""
import argparse
import json
import re
import sys
from pathlib import Path


class Unknown(Exception):
    pass


def load(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Unknown("invalid_cloud_run_json") from exc
    if not isinstance(value, dict):
        raise Unknown("invalid_cloud_run_json")
    return value


def serving_revision(service):
    traffic = (service.get("status") or {}).get("traffic")
    if not isinstance(traffic, list) or not traffic:
        raise Unknown("missing_observed_traffic")
    total, full = 0, []
    for entry in traffic:
        if not isinstance(entry, dict):
            raise Unknown("malformed_observed_traffic")
        pct = entry.get("percent", 0)
        if type(pct) is not int or not 0 <= pct <= 100:
            raise Unknown("malformed_observed_traffic")
        total += pct
        if pct == 100:
            full.append(entry.get("revisionName"))
    if total != 100 or len(full) != 1 or not isinstance(full[0], str) or not full[0]:
        raise Unknown("ambiguous_serving_revision")
    return full[0]


def check(service, revision, expected_service):
    name = serving_revision(service)
    if (service.get("metadata") or {}).get("name") != expected_service:
        raise Unknown("wrong_worker_service")
    if (revision.get("metadata") or {}).get("name") != name:
        raise Unknown("revision_changed_or_mismatched")
    ready = [c.get("status") for c in (revision.get("status") or {}).get("conditions", [])
             if isinstance(c, dict) and c.get("type") == "Ready"]
    if ready != ["True"]:
        raise Unknown("serving_revision_not_ready")
    containers = (revision.get("spec") or {}).get("containers")
    if not isinstance(containers, list) or len(containers) != 1 or not isinstance(containers[0], dict):
        raise Unknown("ambiguous_worker_containers")
    envs = containers[0].get("env")
    if not isinstance(envs, list):
        raise Unknown("missing_worker_environment")
    matches = [e for e in envs if isinstance(e, dict) and e.get("name") == "SCAN_EVIDENCE_SIGNING_KEY"]
    if len(matches) != 1:
        raise Unknown("missing_or_duplicate_signing_binding")
    entry = matches[0]
    if "value" in entry:
        raise Unknown("plaintext_signing_binding")
    ref = (entry.get("valueFrom") or {}).get("secretKeyRef")
    if not isinstance(ref, dict):
        raise Unknown("missing_secret_reference")
    secret, version = ref.get("name"), ref.get("key")
    if not isinstance(secret, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", secret):
        raise Unknown("invalid_secret_name")
    if not isinstance(version, str) or not re.fullmatch(r"[1-9][0-9]*", version):
        raise Unknown("unversioned_secret_reference")
    return name, secret, version


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", required=True)
    parser.add_argument("--revision")
    parser.add_argument("--expected-service", default="fixlist-standard150-worker")
    args = parser.parse_args()
    try:
        service = load(args.service)
        if not args.revision:
            print(serving_revision(service))
            return 0
        name, secret, version = check(service, load(args.revision), args.expected_service)
        print(f"signing_reference=METADATA_ONLY revision={name} secret={secret} version={version}")
        print("signing_runtime_and_base44_persistence=UNVERIFIED")
        return 0
    except Unknown as exc:
        print(f"signing_reference=INDETERMINATE reason={exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
