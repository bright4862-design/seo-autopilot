#!/usr/bin/env python3
"""Prove a dispatch-gateway deployment actually serves the bytes it just built.

Split into phases because they fail for different reasons and on different
timelines.

``plan_revision`` names the revision *before* the deploy runs. Reading the name
back afterwards from ``status.latestCreatedRevisionName`` returns whichever
revision was created most recently on the service, and nothing stops a second
deployment -- a direct script call, another principal -- from landing between
the deploy and the read. Reserving the name up front means the revision this
run promotes and attests can only be the revision this run built.

``verify_created_revision`` reads the reserved revision back by exact name and
requires it to be Ready. It is the proof that our own deploy produced it.

``verify_control_plane`` reads what Cloud Run has been told: which revision
holds traffic, what image that revision pulled, what environment it carries. It
is deterministic the moment the promotion returns, so a failure here is final.

``verify_runtime_health`` reads what a customer actually gets back from the
untagged service URL. That URL is the real customer route, and during traffic
propagation it can still be answered by the revision being drained. Every other
health field -- source_sha included -- is identical across two revisions built
from the same commit, so only the executing revision distinguishes them. The
gateway reports it from K_REVISION, which the container receives and a caller
cannot forge. Because propagation is a race, this phase is retried by the
caller until a deadline rather than failed on first mismatch.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any


# Cloud Run revision names are RFC1035 labels capped at 63 characters.
REVISION_NAME_PATTERN = re.compile(r"^[a-z]([-a-z0-9]*[a-z0-9])?$")
REVISION_SUFFIX_PATTERN = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
MAX_REVISION_NAME_LENGTH = 63


class VerificationError(Exception):
    """A deployment claim that the live service does not support."""


def plan_revision(service_name: str, suffix: str) -> str:
    """The revision name this deployment reserves, decided before deploying.

    Cloud Run refuses to create a revision whose name already exists, so a
    validated per-invocation suffix is what binds the promoted revision to this
    run. Nothing here reads service state, by design.
    """
    if not service_name:
        raise VerificationError("Revision planning needs the Cloud Run service name")
    if not REVISION_SUFFIX_PATTERN.match(suffix):
        raise VerificationError(
            f"Revision suffix {suffix!r} is not lowercase alphanumeric with "
            "internal dashes"
        )
    name = f"{service_name}-{suffix}"
    if len(name) > MAX_REVISION_NAME_LENGTH:
        raise VerificationError(
            f"Planned revision {name!r} is {len(name)} characters, over the "
            f"Cloud Run limit of {MAX_REVISION_NAME_LENGTH}"
        )
    if not REVISION_NAME_PATTERN.match(name):
        raise VerificationError(f"Planned revision {name!r} is not a valid revision name")
    return name


def revision_env(revision: dict[str, Any]) -> dict[str, str]:
    containers = revision.get("spec", {}).get("containers") or [{}]
    return {
        str(item.get("name")): str(item.get("value") or "")
        for item in (containers[0].get("env") or [])
    }


def _require_source_sha(revision: dict[str, Any], expected_source_sha: str, where: str) -> None:
    actual = revision_env(revision).get("FIXLIST_GATEWAY_SOURCE_SHA")
    if actual != expected_source_sha:
        raise VerificationError(
            f"{where} FIXLIST_GATEWAY_SOURCE_SHA is {actual!r}, expected "
            f"{expected_source_sha!r}"
        )


def serving_revision(service: dict[str, Any]) -> str:
    """The revision holding the largest traffic share, from status not spec.

    ``spec.template`` is whatever the last deploy asked for; a deploy that
    changed nothing customers reach still updates it. Only ``status.traffic``
    says what is being served. ``status.latestCreatedRevisionName`` is not
    consulted anywhere in this module: it names the newest revision on the
    service, which is not necessarily one this deployment created.
    """
    best_name, best_percent = "", -1
    for item in service.get("status", {}).get("traffic") or []:
        percent = int(item.get("percent") or 0)
        if percent > best_percent:
            best_name, best_percent = str(item.get("revisionName") or ""), percent
    return best_name


def verify_created_revision(
    revision: dict[str, Any],
    expected_revision: str,
    expected_source_sha: str,
) -> dict[str, str]:
    """The reserved revision exists, is Ready, and carries our source SHA."""
    name = str(revision.get("metadata", {}).get("name") or "")
    if name != expected_revision:
        raise VerificationError(
            f"Deploy produced revision {name!r}, not the revision this deployment "
            f"reserved {expected_revision!r}"
        )

    conditions = {
        str(item.get("type")): item
        for item in revision.get("status", {}).get("conditions") or []
    }
    ready = conditions.get("Ready", {})
    if str(ready.get("status") or "") != "True":
        raise VerificationError(
            f"Revision {expected_revision} is not Ready "
            f"(status={ready.get('status')!r}, reason={ready.get('reason')!r})"
        )

    _require_source_sha(revision, expected_source_sha, f"Revision {expected_revision}")
    return {"created_revision": expected_revision}


def verify_control_plane(
    service: dict[str, Any],
    revision: dict[str, Any],
    expected_revision: str,
    expected_source_sha: str,
) -> dict[str, str]:
    serving = serving_revision(service)
    if serving != expected_revision:
        raise VerificationError(
            f"Traffic serves {serving!r}, not the revision this deployment created "
            f"{expected_revision!r}"
        )

    percent = sum(
        int(item.get("percent") or 0)
        for item in service.get("status", {}).get("traffic") or []
        if item.get("revisionName") == expected_revision
    )
    if percent != 100:
        raise VerificationError(
            f"Serving traffic on {expected_revision} is {percent}%, expected 100%"
        )

    digest = str(revision.get("status", {}).get("imageDigest") or "")
    if "@sha256:" not in digest:
        raise VerificationError(
            f"Revision {expected_revision} has no immutable image digest"
        )

    containers = service.get("spec", {}).get("template", {}).get("spec", {}).get(
        "containers"
    ) or [{}]
    template_image = str(containers[0].get("image") or "")
    if template_image != digest:
        raise VerificationError(
            f"Serving digest {digest} does not equal the image this deployment "
            f"built {template_image}"
        )

    _require_source_sha(revision, expected_source_sha, "Serving revision")

    return {"serving_revision": expected_revision, "serving_image_digest": digest}


def verify_runtime_health(
    health: dict[str, Any],
    expected_revision: str,
    expected_source_sha: str,
    expected_contract_version: str,
    queue_path: str,
    drain_queue_path: str,
    worker_origin: str,
) -> dict[str, str]:
    def require(name: str, actual: Any, expected: Any) -> None:
        if actual != expected:
            raise VerificationError(
                f"Gateway /health {name} is {actual!r}, expected {expected!r}"
            )

    require("ok", health.get("ok"), True)
    require("service", health.get("service"), "fixlist-dispatch-gateway")
    require("queue", health.get("queue"), queue_path)
    require("drain_queue", health.get("drain_queue"), drain_queue_path)
    require("worker_origin", health.get("worker_origin"), worker_origin)
    require("contract_version", health.get("contract_version"), expected_contract_version)
    require("source_sha", health.get("source_sha"), expected_source_sha)
    # The one field that distinguishes two revisions built from the same commit.
    require("revision", health.get("revision"), expected_revision)

    return {
        "runtime_revision": str(health["revision"]),
        "runtime_source_sha": str(health["source_sha"]),
    }


def _load(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-revision", action="store_true")
    parser.add_argument("--service")
    parser.add_argument("--revision-suffix")
    parser.add_argument("--service-json")
    parser.add_argument("--revision-json")
    parser.add_argument("--created-revision-json")
    parser.add_argument("--health-json")
    parser.add_argument("--expected-revision")
    parser.add_argument("--expected-source-sha")
    parser.add_argument("--expected-contract-version", default="")
    parser.add_argument("--queue-path", default="")
    parser.add_argument("--drain-queue-path", default="")
    parser.add_argument("--worker-origin", default="")
    args = parser.parse_args(argv)

    if not args.plan_revision:
        for required in ("expected_revision", "expected_source_sha"):
            if not getattr(args, required):
                parser.error(f"--{required.replace('_', '-')} is required")

    try:
        if args.plan_revision:
            if not args.service or not args.revision_suffix:
                parser.error("--plan-revision needs --service and --revision-suffix")
            proven = {
                "planned_revision": plan_revision(args.service, args.revision_suffix)
            }
        elif args.health_json:
            proven = verify_runtime_health(
                _load(args.health_json),
                args.expected_revision,
                args.expected_source_sha,
                args.expected_contract_version,
                args.queue_path,
                args.drain_queue_path,
                args.worker_origin,
            )
        elif args.created_revision_json:
            proven = verify_created_revision(
                _load(args.created_revision_json),
                args.expected_revision,
                args.expected_source_sha,
            )
        else:
            if not args.service_json or not args.revision_json:
                parser.error("control-plane mode needs --service-json and --revision-json")
            proven = verify_control_plane(
                _load(args.service_json),
                _load(args.revision_json),
                args.expected_revision,
                args.expected_source_sha,
            )
    except VerificationError as error:
        print(f"Refusing gateway deployment: {error}", file=sys.stderr)
        return 2

    for key, value in proven.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
