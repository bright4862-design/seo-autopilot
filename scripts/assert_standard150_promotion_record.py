#!/usr/bin/env python3
"""Block customer-serving worker promotion when canonical release is unaccepted.

Zero-traffic staging remains available for candidate acceptance. This source
gate is necessary, not sufficient: it does not prove deployed Base44 bytes,
worker /revision, admission state or a signed customer scan.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
FINGERPRINT16 = re.compile(r"[0-9a-f]{16}\Z")


class PromotionRecordError(ValueError):
    """Release record cannot authorize promotion."""


def require_unchanged_accepted_source(root: Path, accepted_sha: str, source_sha: str) -> None:
    """Permit release-record/docs commits but refuse changed executable trees.

    The frozen record normally lands *after* its accepted git_commit. Git
    ancestry alone would also authorize arbitrary subsequent source changes.
    Compare the endpoint trees, not the commit subjects or intermediate history;
    a reverted edit is safe only if the final tracked bytes match the accepted
    source. This check is a metadata precondition, not live deployment proof.
    """
    try:
        delta = subprocess.run(
            ["git", "-C", str(root), "diff", "--name-only", "-z",
             "--no-renames", "--no-ext-diff", "--no-textconv",
             "--ignore-submodules=none", accepted_sha, source_sha, "--"],
            check=False, capture_output=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PromotionRecordError("accepted_source_tree_unavailable") from exc
    changed = getattr(delta, "stdout", None)
    if delta.returncode != 0 or not isinstance(changed, bytes) or (changed and not changed.endswith(b"\0")):
        raise PromotionRecordError("accepted_source_tree_unverifiable")
    for raw in changed.split(b"\0"):
        if not raw:
            continue
        path = raw.decode("utf-8", "surrogateescape")
        if path == "data/beta-crawler-revision.json":
            continue
        # A post-acceptance report or narrative documentation is legitimate;
        # scripts, workflow YAML, configs and executable docs files are not.
        if (path.startswith("docs/") and path.endswith(".md")
                and all(part not in (".", "..", "") for part in path.split("/"))):
            continue
        raise PromotionRecordError("accepted_source_tree_drift")


def verify_promotion_record(root: Path, source_sha: str) -> str:
    """Check frozen metadata and ancestry, without trusting runtime claims."""
    if not SHA40.fullmatch(source_sha):
        raise PromotionRecordError("source_sha_invalid")
    try:
        record = json.loads((root / "data/beta-crawler-revision.json").read_text("utf-8"))
    except (OSError, ValueError) as exc:
        raise PromotionRecordError("release_record_unreadable") from exc
    if not isinstance(record, dict) or record.get("status") != "frozen_beta":
        raise PromotionRecordError("release_not_accepted_candidate")
    accepted_sha = record.get("git_commit")
    if not isinstance(accepted_sha, str) or not SHA40.fullmatch(accepted_sha):
        raise PromotionRecordError("accepted_git_commit_missing")
    # The record is committed after the accepted source; matching HEAD exactly
    # would be impossible without rewriting the HEAD that contains this record.
    try:
        ancestry = subprocess.run(
            ["git", "-C", str(root), "merge-base", "--is-ancestor", accepted_sha, source_sha],
            check=False, capture_output=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PromotionRecordError("accepted_source_ancestry_unavailable") from exc
    if ancestry.returncode != 0:
        raise PromotionRecordError("accepted_git_commit_not_ancestor")
    require_unchanged_accepted_source(root, accepted_sha, source_sha)
    report = record.get("acceptance_report")
    if not isinstance(report, str) or not report:
        raise PromotionRecordError("acceptance_report_missing")
    path = Path(report)
    if (path.is_absolute() or not path.parts or path.parts[0] != "docs"
            or path.suffix != ".md" or any(part in (".", "..") for part in path.parts)):
        raise PromotionRecordError("acceptance_report_path_invalid")
    document = root / path
    if (document.is_symlink() or not document.is_file()
            or not document.resolve().is_relative_to(root.resolve())):
        raise PromotionRecordError("acceptance_report_unavailable")
    if not document.read_text("utf-8").strip():
        raise PromotionRecordError("acceptance_report_empty")
    components = record.get("component_versions")
    if (not isinstance(components, dict) or not components
            or any(not isinstance(k, str) or not re.fullmatch(r"[a-z0-9_]+", k)
                   or not isinstance(v, str) or not v.strip()
                   for k, v in components.items())):
        raise PromotionRecordError("release_components_invalid")
    calculated = hashlib.sha256(
        json.dumps(components, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    fingerprint = record.get("fingerprint")
    if (not isinstance(fingerprint, str)
            or not FINGERPRINT16.fullmatch(fingerprint)
            or fingerprint != calculated):
        raise PromotionRecordError("release_fingerprint_inconsistent")
    return fingerprint


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        fingerprint = verify_promotion_record(args.repo_root, args.source_sha)
    except (PromotionRecordError, UnicodeError, OSError) as exc:
        print(f"PROMOTION_RECORD_BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(f"PROMOTION_RECORD_METADATA_OK fingerprint={fingerprint}")
    print("Live /revision, Base44 package, closed barrier and signed customer canary still required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
