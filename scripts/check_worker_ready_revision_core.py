#!/usr/bin/env python3
"""Read-only proof of the exact Ready Cloud Run revision's worker identity.

The service *template* is desired state and can lead the serving/Ready revision.
Do not print env contents or signing-key metadata values.
"""
from __future__ import annotations

import argparse
import json
import sys


class ReadyRevisionError(ValueError):
    pass


def unique_members(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReadyRevisionError("duplicate JSON member")
        result[key] = value
    return result


def verify(document, args):
    if not isinstance(document, dict) or not isinstance(document.get("metadata"), dict):
        raise ReadyRevisionError("Ready revision metadata unavailable")
    if document["metadata"].get("name") != args.revision:
        raise ReadyRevisionError("Ready revision name mismatch")
    spec = document.get("spec")
    if not isinstance(spec, dict):
        raise ReadyRevisionError("Ready revision spec unavailable")
    containers = spec.get("containers")
    if not isinstance(containers, list) or len(containers) != 1 or not isinstance(containers[0], dict):
        raise ReadyRevisionError("Ready revision requires exactly one container")
    container = containers[0]
    if container.get("image") != args.image:
        raise ReadyRevisionError("Ready revision image mismatch")
    if spec.get("serviceAccountName") != args.runtime_sa:
        raise ReadyRevisionError("Ready revision runtime service account mismatch")
    if spec.get("timeoutSeconds") != 480 or spec.get("containerConcurrency") != 1:
        raise ReadyRevisionError("Ready revision timeout/concurrency mismatch")
    items = container.get("env")
    if not isinstance(items, list):
        raise ReadyRevisionError("Ready revision environment unavailable")
    env = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"]:
            raise ReadyRevisionError("malformed Ready revision environment")
        if item["name"] in env:
            raise ReadyRevisionError("duplicate Ready revision environment name")
        env[item["name"]] = item

    for name, expected in (
        ("TASKS_INVOKER_SERVICE_ACCOUNT", args.invoker_sa),
        ("FIXLIST_WORKER_SOURCE_SHA", args.source_sha),
    ):
        item = env.get(name)
        if not isinstance(item, dict) or item.get("value") != expected or "valueFrom" in item:
            raise ReadyRevisionError(name + " on Ready revision is not pinned")

    grok = env.get("GROK_PROXY_ENABLED")
    if grok is not None and (
        "valueFrom" in grok or
        not isinstance(grok.get("value"), str) or
        grok["value"].lower() != "false"
    ):
        raise ReadyRevisionError("Grok is not disabled on Ready revision")
    if "GROK_CHAT_ENABLED" in env:
        raise ReadyRevisionError("GROK_CHAT_ENABLED no-op found on Ready revision")

    signing = env.get("SCAN_EVIDENCE_SIGNING_KEY")
    if not isinstance(signing, dict) or "value" in signing:
        raise ReadyRevisionError("Ready revision signing reference missing or plaintext")
    value_from = signing.get("valueFrom")
    ref = value_from.get("secretKeyRef") if isinstance(value_from, dict) else None
    if not isinstance(ref, dict) or ref.get("name") != args.signing_secret or str(ref.get("key")) != args.signing_version:
        raise ReadyRevisionError("Ready revision signing secret/version mismatch")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--runtime-sa", required=True)
    parser.add_argument("--invoker-sa", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--signing-secret", required=True)
    parser.add_argument("--signing-version", required=True)
    args = parser.parse_args(argv)
    try:
        raw = sys.stdin.buffer.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ReadyRevisionError("Ready revision metadata exceeds size limit")
        document = json.loads(raw, object_pairs_hook=unique_members)
        verify(document, args)
    except (ValueError, TypeError, AttributeError) as exc:
        print("READY_REVISION_CORE_UNVERIFIED: " + str(exc), file=sys.stderr)
        return 1
    print("READY_REVISION_CORE_MATCH")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
