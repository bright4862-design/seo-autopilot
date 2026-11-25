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
BASE44_ROUTES = "data/base44-function-routes.json"
GENERATED_V9_ROUTES = "data/generated-staged-v9-routes.json"
SCANNER_FUNCTIONS = (
    "startStandardScanJob", "durableScanWorkerControl", "persistDurableScanAuthority",
    "persistLimitedScanResult", "getCustomerScanResult", "deleteCustomerScanData",
)


class PromotionRecordError(ValueError):
    """Release record cannot authorize promotion."""


def verify_active_v9_packages(root: Path, accepted_sha: str, source_sha: str, deployment: str) -> None:
    packages = [f"base44/functions/{name}{generation}" for generation in ("V8", "V9") for name in SCANNER_FUNCTIONS]
    if deployment == "recover-functions":
        packages.append("base44/functions/fixlistStagedRuntimeControl")
    if deployment in {"release-functions", "site-and-functions"}:
        packages.extend(f"base44/functions/{name}" for name in ("createAccessCheckout", "stripeWebhook", "ownerScanDebugControl"))

    def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", "-C", str(root), *args], check=check,
                              capture_output=True, text=True, timeout=10)

    def recorded_routes(commit: str, file: str) -> dict:
        value = json.loads(git("show", f"{commit}:{file}").stdout)
        if not isinstance(value, dict):
            raise ValueError("invalid routes")
        return value

    def physical_v9(commit: str) -> dict:
        functions = recorded_routes(commit, GENERATED_V9_ROUTES)["functions"]
        return {name: functions[f"{name}V9"]["route_name"] for name in SCANNER_FUNCTIONS}

    try:
        comparison = git("diff", "--no-ext-diff", "--quiet", accepted_sha, source_sha, "--",
                         GENERATED_V9_ROUTES, "base44/shared", *packages, check=False)
        if comparison.returncode == 1:
            raise PromotionRecordError("active_v9_packages_differ_from_accepted_source")
        if comparison.returncode != 0:
            raise PromotionRecordError("active_v9_accepted_packages_unverified")
        if deployment == "site-and-functions":
            if git("rev-parse", "--is-shallow-repository").stdout.strip() != "false":
                raise PromotionRecordError("active_v9_public_route_history_unavailable")
            current = physical_v9(source_sha)
            history = git("log", "--full-history", "--format=%H", source_sha, "--",
                          BASE44_ROUTES, GENERATED_V9_ROUTES).stdout.splitlines()
            for prior in history:
                if prior != source_sha and recorded_routes(prior, BASE44_ROUTES).get("generation") == "v9":
                    if physical_v9(prior) != current:
                        raise PromotionRecordError("active_v9_site_would_omit_earlier_public_aliases")
    except PromotionRecordError:
        raise
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as exc:
        raise PromotionRecordError("active_v9_accepted_packages_or_history_unverified") from exc


WORKER_IMAGE_SOURCE_PATHS = (
    # Worker image inputs and the scripts/workflow that authorize its promotion.
    # The accepted commit may precede its report/manifest commit; subsequent
    # runtime OR release-control changes require fresh acceptance. This is
    # defense in depth: a trusted, reviewed runner must still invoke this gate.
    "scanner-api/app",
    "Dockerfile",  # Actual Dockerfile copied by the Cloud Build verified context.
    "scanner-api/Dockerfile",
    "scanner-api/requirements.txt",
    "data/cross-runtime-release-components.json",
    "scripts/staged_candidate_cloudbuild.py",
    "scripts/verify-fixlist-static-egress-canary.sh",
    "cloudbuild.durable-worker.yaml",
    "cloudbuild.durable-worker-static-egress-canary.yaml",
    "scripts/build-worker-candidate.sh",
    # Post-acceptance edits to the promotion command, its own predicate, the
    # exact-main guard or its Actions launcher must not reuse old acceptance.
    "scripts/assert_standard150_promotion_record.py",
    "scripts/assert_standard150_rollback_readback.py",
    "scripts/assert_standard150_rollback_ownership.py",
    "scripts/fixlist-cloud-operator.sh",
    "scripts/lib/release-source-guard.sh",
    ".github/workflows/fixlist-cloud-operator.yml",
)


def verify_accepted_worker_image_source(root: Path, accepted_sha: str, source_sha: str) -> None:
    try:
        comparison = subprocess.run(
            ["git", "-C", str(root), "diff", "--no-ext-diff", "--quiet",
             accepted_sha, source_sha, "--", *WORKER_IMAGE_SOURCE_PATHS],
            check=False, capture_output=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PromotionRecordError("accepted_worker_source_unverified") from exc
    if comparison.returncode == 1:
        raise PromotionRecordError("worker_source_differs_from_accepted_commit")
    if comparison.returncode != 0:
        raise PromotionRecordError("accepted_worker_source_unverified")


def verify_promotion_record(root: Path, source_sha: str, base44_v9: str | None = None,
                            worker_promotion: bool = False) -> str:
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
    if base44_v9:
        verify_active_v9_packages(root, accepted_sha, source_sha, base44_v9)
    if worker_promotion:
        verify_accepted_worker_image_source(root, accepted_sha, source_sha)
    return fingerprint


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--base44-v9", choices=("scanner-functions", "release-functions", "site-and-functions", "recover-functions"))
    parser.add_argument("--worker-promotion", action="store_true",
                        help="Require worker image, build and promotion-control inputs unchanged since acceptance")
    args = parser.parse_args()
    try:
        fingerprint = verify_promotion_record(args.repo_root, args.source_sha, args.base44_v9,
                                              worker_promotion=args.worker_promotion)
    except (PromotionRecordError, UnicodeError, OSError) as exc:
        print(f"PROMOTION_RECORD_BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(f"PROMOTION_RECORD_METADATA_OK fingerprint={fingerprint}")
    print("Live /revision, Base44 package, closed barrier and signed customer canary still required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
