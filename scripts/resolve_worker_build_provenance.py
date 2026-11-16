#!/usr/bin/env python3
"""Read-only Cloud Run worker provenance: bind a revision's resolved digest to one Cloud Build.

A match is necessary, not release acceptance or authenticated runtime attestation.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")


class ProvenanceError(ValueError):
    pass


def image_repository(image: object) -> tuple[str, str | None]:
    if not isinstance(image, str) or not image or any(c.isspace() for c in image):
        raise ProvenanceError("image_reference_invalid")
    if "@" in image:
        repo, digest = image.split("@", 1)
        if not repo or not DIGEST.fullmatch(digest):
            raise ProvenanceError("image_reference_invalid")
        return repo, digest
    # Only the last colon after the last slash is a tag separator; registries
    # may have port numbers.
    last_slash = image.rfind("/")
    colon = image.rfind(":")
    if colon > last_slash:
        repo, tag = image[:colon], image[colon + 1:]
        if not repo or not tag or "@" in tag:
            raise ProvenanceError("image_reference_invalid")
        return repo, None
    return image, None


def selected_revision(revision: object) -> tuple[str, str]:
    if not isinstance(revision, dict):
        raise ProvenanceError("revision_invalid")
    try:
        container = revision["spec"]["containers"]
        image = container[0]["image"]
        resolved = revision["status"]["imageDigest"]
    except (KeyError, IndexError, TypeError):
        raise ProvenanceError("revision_resolved_digest_missing") from None
    if not isinstance(container, list) or len(container) != 1:
        raise ProvenanceError("revision_container_count_unsupported")
    repo, specified_digest = image_repository(image)
    if not isinstance(resolved, str) or not resolved:
        raise ProvenanceError("revision_resolved_digest_missing")
    if "@" in resolved:
        resolved_repo, resolved_digest = image_repository(resolved)
        if repo != resolved_repo:
            raise ProvenanceError("revision_resolved_repository_mismatch")
    else:
        resolved_digest = resolved
    if not DIGEST.fullmatch(resolved_digest):
        raise ProvenanceError("revision_resolved_digest_invalid")
    if specified_digest is not None and specified_digest != resolved_digest:
        raise ProvenanceError("revision_spec_status_digest_mismatch")
    return repo, resolved_digest


def release_sha_for_revision(revision: object, builds: object) -> tuple[str, str]:
    repo, digest = selected_revision(revision)
    if not isinstance(builds, list):
        raise ProvenanceError("build_list_invalid")
    matches: list[dict] = []
    for build in builds:
        if not isinstance(build, dict):
            continue
        images = (build.get("results") or {}).get("images") or []
        if not isinstance(images, list):
            continue
        for item in images:
            if not isinstance(item, dict):
                continue
            try:
                item_repo, _ = image_repository(item.get("name"))
            except ProvenanceError:
                continue
            if item_repo == repo and item.get("digest") == digest:
                matches.append(build)
                break
    if not matches:
        raise ProvenanceError("resolved_digest_build_not_found")
    if len(matches) != 1:
        raise ProvenanceError("resolved_digest_multiple_builds")
    build = matches[0]
    if build.get("status") != "SUCCESS":
        raise ProvenanceError("resolved_digest_build_not_successful")
    sha = (build.get("substitutions") or {}).get("_RELEASE_SHA")
    if not isinstance(sha, str) or not COMMIT.fullmatch(sha):
        raise ProvenanceError("release_sha_missing_or_invalid")
    build_id = build.get("id")
    if not isinstance(build_id, str) or not build_id:
        raise ProvenanceError("build_id_missing")
    return sha, build_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision-json", required=True)
    args = parser.parse_args()
    try:
        with open(args.revision_json, encoding="utf-8") as file:
            revision = json.load(file)
        builds = json.load(sys.stdin)
        sha, build_id = release_sha_for_revision(revision, builds)
    except (OSError, json.JSONDecodeError, ProvenanceError) as exc:
        reason = str(exc) if isinstance(exc, ProvenanceError) else "provenance_json_unavailable"
        print(f"INDETERMINATE: {reason}", file=sys.stderr)
        return 1
    print(f"matched immutable Cloud Build {build_id}", file=sys.stderr)
    print(sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
