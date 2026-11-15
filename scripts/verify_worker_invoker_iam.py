#!/usr/bin/env python3
"""Fail closed when a Standard 150 Cloud Run service bypasses IAM invocation checks.

Reads only the existing 'gcloud run services describe --format=json' result.
Does not invoke, deploy, change IAM, inspect secret payloads, or print metadata.
"""
import json
import sys


ANNOTATION = "run.googleapis.com/invoker-iam-disabled"


def unique_members(pairs):
    obj = {}
    for name, value in pairs:
        if name in obj:
            raise ValueError("duplicate JSON member")
        obj[name] = value
    return obj


def invoker_iam_enforced(payload):
    service = json.loads(payload, object_pairs_hook=unique_members)
    if not isinstance(service, dict):
        raise ValueError("service metadata must be a JSON object")
    metadata = service.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("service metadata is missing or malformed")
    annotations = metadata.get("annotations", {})
    if not isinstance(annotations, dict):
        raise ValueError("service annotations are malformed")
    # Cloud Run defaults to enforcing IAM; the v1 service annotation is
    # specifically used to disable it, independently of IAM role bindings.
    value = annotations.get(ANNOTATION, "false")
    if value != "false":
        raise ValueError("Cloud Run invoker IAM check is disabled or ambiguous")
    return True


def main():
    try:
        invoker_iam_enforced(sys.stdin.read())
    except (ValueError, TypeError, UnicodeError):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
