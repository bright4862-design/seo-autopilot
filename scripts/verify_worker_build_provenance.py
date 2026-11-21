#!/usr/bin/env python3
"""Read-only, fail-closed worker build provenance for one exact Cloud Run revision.

Usage: --revision-json R --builds-json B --revision REV --service SERVICE
The *only* stdout on success is the immutable 40-character source SHA.
This check does not establish serving traffic, runtime fingerprint, Base44
package identity, or release acceptance. Those are separate operator gates.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

SOURCE_SHA = re.compile(r"[0-9a-f]{40}\Z")
IMAGE_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
IMAGE_REPOSITORY = re.compile(r"[a-z0-9.-]+(?:/[a-zA-Z0-9._-]+)+\Z")


class ProvenanceUnavailable(ValueError):
    """Insufficient or contradictory control-plane evidence: refuse green."""


def image_repository(ref: object) -> str:
    """Separate the image *repository* from either a tag or digest.

    Only fixed-form, fully qualified image references are accepted. Never use
    the old split(':')[0] heuristic: registry ports and mutable tags are not
    proof of image identity.
    """
    if not isinstance(ref, str) or not ref or ref != ref.strip():
        raise ProvenanceUnavailable("image_reference_missing")
    if "@" in ref:
        repo, separator, digest = ref.partition("@")
        if not separator or not IMAGE_DIGEST.fullmatch(digest):
            raise ProvenanceUnavailable("image_reference_digest_invalid")
    else:
        path, slash, leaf = ref.rpartition("/")
        if not slash or ":" not in leaf:
            raise ProvenanceUnavailable("image_reference_tag_missing")
        basename, tag = leaf.rsplit(":", 1)
        if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", tag):
            raise ProvenanceUnavailable("image_reference_tag_invalid")
        repo = f"{path}/{basename}"
    if not IMAGE_REPOSITORY.fullmatch(repo):
        raise ProvenanceUnavailable("image_repository_invalid")
    return repo


def derive_source_sha(revision: object, builds: object, *, expected_revision: str, expected_service: str) -> tuple[str, str, str]:
    """Return (source_sha, build_id, resolved_digest_ref) for exactly one match."""
    if not isinstance(revision, dict) or not isinstance(builds, list):
        raise ProvenanceUnavailable("revision_or_build_list_invalid")
    meta = revision.get("metadata") or {}
    status = revision.get("status") or {}
    spec = revision.get("spec") or {}
    if not isinstance(meta, dict) or not isinstance(status, dict) or not isinstance(spec, dict):
        raise ProvenanceUnavailable("revision_shape_invalid")
    if not expected_revision or meta.get("name") != expected_revision:
        raise ProvenanceUnavailable("revision_name_mismatch")
    labels = meta.get("labels") or {}
    if not isinstance(labels, dict) or labels.get("serving.knative.dev/service") != expected_service:
        raise ProvenanceUnavailable("revision_service_mismatch")
    conditions = status.get("conditions") or []
    ready = [c for c in conditions if isinstance(c, dict) and c.get("type") == "Ready"] if isinstance(conditions, list) else []
    if len(ready) != 1 or str(ready[0].get("status") or "").lower() != "true":
        raise ProvenanceUnavailable("revision_not_ready")
    containers = spec.get("containers") or []
    if not isinstance(containers, list) or len(containers) != 1 or not isinstance(containers[0], dict):
        raise ProvenanceUnavailable("revision_container_ambiguous")
    desired_repo = image_repository(containers[0].get("image"))
    resolved_ref = status.get("imageDigest")
    if not isinstance(resolved_ref, str) or "@" not in resolved_ref:
        raise ProvenanceUnavailable("resolved_image_digest_missing")
    resolved_repo, resolved_digest = resolved_ref.rsplit("@", 1)
    if not IMAGE_DIGEST.fullmatch(resolved_digest) or image_repository(resolved_ref) != desired_repo:
        raise ProvenanceUnavailable("resolved_image_digest_mismatch")
    supplied_image = containers[0]["image"]
    if "@" in supplied_image and supplied_image != resolved_ref:
        raise ProvenanceUnavailable("image_spec_and_resolved_digest_disagree")
    matches = []
    for record in builds:
        if not isinstance(record, dict) or record.get("status") != "SUCCESS":
            continue
        release_sha = (record.get("substitutions") or {}).get("_RELEASE_SHA")
        if not isinstance(release_sha, str) or not SOURCE_SHA.fullmatch(release_sha):
            continue
        # This repository's Cloud Build manifest pushes <repository>:<SHA>.
        # Requiring that exact output also prevents a colliding digest from a
        # different image/release being treated as the worker build.
        expected_name = f"{desired_repo}:{release_sha}"
        images = (record.get("results") or {}).get("images") or []
        if not isinstance(images, list):
            continue
        if any(isinstance(img, dict) and img.get("name") == expected_name
               and img.get("digest") == resolved_digest for img in images):
            if not isinstance(record.get("id"), str) or not record["id"].strip():
                raise ProvenanceUnavailable("matching_build_id_missing")
            matches.append((release_sha, record["id"], resolved_ref))
    if not matches:
        raise ProvenanceUnavailable("resolved_digest_has_no_successful_source_pinned_build_in_window")
    if len(matches) != 1:
        raise ProvenanceUnavailable("resolved_digest_has_ambiguous_successful_builds")
    return matches[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("revision-json", "builds-json", "revision", "service"):
        parser.add_argument(f"--{key}", required=True)
    args = parser.parse_args(argv)
    try:
        revision = json.loads(Path(args.revision_json).read_text(encoding="utf-8"))
        builds = json.loads(Path(args.builds_json).read_text(encoding="utf-8"))
        release_sha, build_id, image_ref = derive_source_sha(
            revision, builds, expected_revision=args.revision, expected_service=args.service
        )
    except (ProvenanceUnavailable, OSError, ValueError, TypeError) as exc:
        print(f"INDETERMINATE: worker_build_provenance_{exc}", file=sys.stderr)
        return 2
    print(f"verified image={image_ref} build_id={build_id} source_sha={release_sha}", file=sys.stderr)
    print(release_sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
