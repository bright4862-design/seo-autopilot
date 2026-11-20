#!/usr/bin/env python3
"""Keyless Cloud Run signing-key reference guard.

Never reads signing-key bytes. Selects only a single Ready, 100%-serving
revision, and refuses a desired-template/serving-revision key mismatch.
"""

import json
import re
import sys
from pathlib import Path


def fail(message):
    raise SystemExit("ERROR: " + message)


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def serving_revision(service):
    metadata = service.get("metadata") or {}
    status = service.get("status") or {}
    generation = metadata.get("generation")
    observed = status.get("observedGeneration")
    if generation is None or observed is None:
        fail("Cloud Run service generation observation is missing")
    if str(generation) != str(observed):
        fail("Cloud Run service generation has not been observed")

    traffic = status.get("traffic")
    if not isinstance(traffic, list) or not traffic:
        fail("no observed Cloud Run serving traffic")
    active = []
    for target in traffic:
        if not isinstance(target, dict):
            fail("invalid observed traffic target")
        percent = target.get("percent")
        if type(percent) is not int or percent < 0 or percent > 100:
            fail("invalid observed traffic percentage")
        if percent:
            active.append(target)
    if len(active) != 1 or active[0]["percent"] != 100:
        fail("worker does not have exactly one 100%-serving revision")
    revision = active[0].get("revisionName")
    if not isinstance(revision, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", revision):
        fail("100%-serving revision has no explicit revisionName")
    return revision


def signing_ref(config):
    containers = config.get("containers") if isinstance(config, dict) else None
    if not isinstance(containers, list) or len(containers) != 1:
        fail("expected exactly one worker container")
    env = containers[0].get("env")
    if not isinstance(env, list):
        fail("worker environment is missing")
    matches = [item for item in env if isinstance(item, dict) and item.get("name") == "SCAN_EVIDENCE_SIGNING_KEY"]
    if len(matches) != 1:
        fail("worker signing-key reference is missing or duplicated")
    ref = (matches[0].get("valueFrom") or {}).get("secretKeyRef") or {}
    name, version = ref.get("name"), ref.get("key")
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        fail("worker signing-secret name is invalid")
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]+", version) or int(version) < 1:
        fail("worker signing-secret version must be a pinned positive integer")
    return name, version


def select(service, revision):
    active_name = serving_revision(service)
    metadata = revision.get("metadata") or {}
    if metadata.get("name") != active_name:
        fail("revision metadata does not match observed serving target")
    service_name = (service.get("metadata") or {}).get("name")
    revision_service = (metadata.get("labels") or {}).get("serving.knative.dev/service")
    if not isinstance(service_name, str) or not service_name or revision_service != service_name:
        fail("serving revision lacks matching service ownership metadata")
    conditions = (revision.get("status") or {}).get("conditions") or []
    ready = [item for item in conditions if isinstance(item, dict) and item.get("type") == "Ready"]
    if len(ready) != 1 or ready[0].get("status") != "True":
        fail("100%-serving revision is not confirmed Ready")
    template = ((service.get("spec") or {}).get("template") or {}).get("spec") or {}
    desired_ref = signing_ref(template)
    actual_ref = signing_ref(revision.get("spec") or {})
    if desired_ref != actual_ref:
        fail("desired-template signing key differs from 100%-serving revision")
    return active_name, actual_ref


def main(argv):
    if len(argv) == 3 and argv[1] == "revision-name":
        print(serving_revision(load(argv[2])))
        return
    if len(argv) != 5 or argv[1] not in {"select", "verify"}:
        fail("usage: guard.py revision-name SERVICE | select|verify SERVICE REVISION REF")
    mode, service_path, revision_path, reference_path = argv[1:]
    name, (secret, version) = select(load(service_path), load(revision_path))
    # Keep line one compatible with an eventual shell `read` of the key reference.
    # The second line binds verification to the exact revision selected earlier.
    value = f"{secret} {version}\n{name}\n"
    if mode == "select":
        Path(reference_path).write_text(value, encoding="utf-8")
        print(f"OK - Ready 100%-serving revision {name} uses pinned {secret} version {version}")
    else:
        if Path(reference_path).read_text(encoding="utf-8") != value:
            fail("serving key or revision identity changed since selection; refusing Base44 import")
        print(f"OK - serving revision {name} and pinned key still match")


if __name__ == "__main__":
    main(sys.argv)
