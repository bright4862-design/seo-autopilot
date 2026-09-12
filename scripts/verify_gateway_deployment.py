#!/usr/bin/env python3
"""Prove a dispatch-gateway deployment actually serves the bytes it just built.

Split into two phases because they fail for different reasons and on different
timelines.

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
import sys
from typing import Any


class VerificationError(Exception):
    """A deployment claim that the live service does not support."""


def serving_revision(service: dict[str, Any]) -> str:
    """The revision holding the largest traffic share, from status not spec.

    ``spec.template`` is whatever the last deploy asked for; a deploy that
    changed nothing customers reach still updates it. Only ``status.traffic``
    says what is being served.
    """
    best_name, best_percent = "", -1
    for item in service.get("status", {}).get("traffic") or []:
        percent = int(item.get("percent") or 0)
        if percent > best_percent:
            best_name, best_percent = str(item.get("revisionName") or ""), percent
    return best_name


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

    revision_containers = revision.get("spec", {}).get("containers") or [{}]
    env = {
        item.get("name"): str(item.get("value") or "")
        for item in (revision_containers[0].get("env") or [])
    }
    actual_sha = env.get("FIXLIST_GATEWAY_SOURCE_SHA")
    if actual_sha != expected_source_sha:
        raise VerificationError(
            "Serving revision FIXLIST_GATEWAY_SOURCE_SHA is "
            f"{actual_sha!r}, expected {expected_source_sha!r}"
        )

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
    parser.add_argument("--service-json")
    parser.add_argument("--revision-json")
    parser.add_argument("--health-json")
    parser.add_argument("--expected-revision", required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-contract-version", default="")
    parser.add_argument("--queue-path", default="")
    parser.add_argument("--drain-queue-path", default="")
    parser.add_argument("--worker-origin", default="")
    args = parser.parse_args(argv)

    try:
        if args.health_json:
            proven = verify_runtime_health(
                _load(args.health_json),
                args.expected_revision,
                args.expected_source_sha,
                args.expected_contract_version,
                args.queue_path,
                args.drain_queue_path,
                args.worker_origin,
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
