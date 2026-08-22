"""Frozen beta crawler revision fingerprinting.

A "beta revision" is the exact combination of scanner + review behaviour we
promise a frozen beta scanner delivers. Rather than trust a git SHA alone, we
fingerprint the authoritative version constants that every module already
publishes. The committed record in ``data/beta-crawler-revision.json`` is the
frozen promise; ``collect_component_versions`` is the live truth. A drift check
compares the two so a version bump cannot silently change what "beta" means.
"""

from __future__ import annotations

import hashlib
import json
import re

from .url_frontier_policy import FRONTIER_POLICY_VERSION
from pathlib import Path
from typing import Any

BETA_REVISION_SCHEMA_VERSION = "beta_crawler_revision_v1"
SCANNER_BUILD_REVISION = "authenticated_health_probe_v1"

# Repo-root/data/beta-crawler-revision.json, resolved from this file's location
# (app/ -> scanner-api/ -> repo root).
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REVISION_PATH = REPO_ROOT / "data" / "beta-crawler-revision.json"


CROSS_RUNTIME_COMPONENTS_PATH = Path(__file__).resolve().parents[2] / "data" / "cross-runtime-release-components.json"
CROSS_RUNTIME_SCHEMA_VERSION = "cross_runtime_release_components_v1"


def load_cross_runtime_components(path: Path | None = None) -> dict[str, str]:
    """Read the canonical cross-runtime component markers.

    Base44 functions and the frontend can change release truth, but Python
    cannot import them, so their markers are declared once in a data file and
    merged into the same fingerprint. Fails closed: a missing, malformed, or
    wrongly-versioned input is an error, never an empty merge that would let a
    cross-runtime change slip through without moving the fingerprint.
    """
    source = Path(path) if path is not None else CROSS_RUNTIME_COMPONENTS_PATH
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Cross-runtime release components are missing at {source}.") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Cross-runtime release components at {source} are not valid JSON.") from exc

    if payload.get("schema_version") != CROSS_RUNTIME_SCHEMA_VERSION:
        raise RuntimeError(
            f"Cross-runtime release components must use {CROSS_RUNTIME_SCHEMA_VERSION}."
        )
    components = payload.get("components")
    if not isinstance(components, dict) or not components:
        raise RuntimeError("Cross-runtime release components must declare a non-empty component map.")

    validated: dict[str, str] = {}
    for key, value in components.items():
        if not isinstance(key, str) or not re.fullmatch(r"[a-z0-9_]+", key):
            raise RuntimeError(f"Cross-runtime component key {key!r} must be snake_case.")
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(f"Cross-runtime component {key!r} must be a non-empty string.")
        validated[key] = value
    return validated


def collect_component_versions() -> dict[str, str]:
    """Read the authoritative version constants live from the scanner modules.

    Imports are local so freeze tooling can call this without constructing the
    FastAPI app or paying for heavier imports at module load time.
    """
    from .artifact_filter import ARTIFACT_FILTER_VERSION
    from .canonical_validation import CANONICAL_TARGET_EVIDENCE_VERSION
    from .coverage_authority import COVERAGE_AUTHORITY_EVIDENCE_VERSION
    from .crawler_acceptance import CRAWLER_ACCEPTANCE_VERSION
    from .evidence_quality import EVIDENCE_QUALITY_GATE_VERSION
    from .extract import CANONICAL_HREF_RESOLUTION_VERSION, ROUTE_BOUNDARY_CLASSIFIER_VERSION
    from .indexability_quality import INDEXABILITY_QUALITY_VERSION
    from .navigation_indexability import NAVIGATION_INDEXABILITY_VERSION
    from .metadata_title_evidence import METADATA_EVIDENCE_VERSION, TITLE_EVIDENCE_VERSION
    from .page_evidence_gate import PAGE_EVIDENCE_GATE_VERSION
    from .redirect_validation import REDIRECT_EVIDENCE_VERSION
    from .render_evidence_quality import RENDER_EVIDENCE_QUALITY_VERSION
    from .render_followup import RENDER_FOLLOWUP_VERSION
    from .review import (
        ARCHETYPE_CLASSIFIER_VERSION,
        GROUPED_RECOMMENDATION_EVIDENCE_VERSION,
        ORPHAN_ASSET_EVIDENCE_VERSION,
        PAGE_LEVEL_ASSET_EVIDENCE_VERSION,
        REPRESENTATIVE_PAGE_VERSION,
        QUALITY_GATE_VERSION,
        REVIEW_VERSION,
        ZERO_FIX_CONFIDENCE_VERSION,
    )
    from .review_calibration import CALIBRATION_VERSION, IMAGE_ALT_EVIDENCE_VERSION
    from .sampling import SAMPLING_VERSION
    from .scan_timing import SITEMAP_TIME_RESERVATION_VERSION
    from .scanner import FINAL_URL_DEDUP_VERSION, RENDER_EVIDENCE_VERSION, VERSION
    from .trust_discovery import TRUST_DISCOVERY_VERSION, TRUST_FINDING_GATE_VERSION

    components = {
        "scanner_version": VERSION,
        "scanner_build_revision": SCANNER_BUILD_REVISION,
        "artifact_filter_version": ARTIFACT_FILTER_VERSION,
        "route_boundary_classifier_version": ROUTE_BOUNDARY_CLASSIFIER_VERSION,
        "final_url_dedup_version": FINAL_URL_DEDUP_VERSION,
        "canonical_target_evidence_version": CANONICAL_TARGET_EVIDENCE_VERSION,
        "canonical_href_resolution_version": CANONICAL_HREF_RESOLUTION_VERSION,
        "redirect_evidence_version": REDIRECT_EVIDENCE_VERSION,
        "render_evidence_version": RENDER_EVIDENCE_VERSION,
        "sampling_version": SAMPLING_VERSION,
        "sitemap_time_reservation_version": SITEMAP_TIME_RESERVATION_VERSION,
        "render_followup_version": RENDER_FOLLOWUP_VERSION,
        "review_version": REVIEW_VERSION,
        "grouped_recommendation_evidence_version": GROUPED_RECOMMENDATION_EVIDENCE_VERSION,
        "archetype_classifier_version": ARCHETYPE_CLASSIFIER_VERSION,
        "representative_page_version": REPRESENTATIVE_PAGE_VERSION,
        "page_level_asset_evidence_version": PAGE_LEVEL_ASSET_EVIDENCE_VERSION,
        "orphan_asset_evidence_version": ORPHAN_ASSET_EVIDENCE_VERSION,
        "zero_fix_confidence_version": ZERO_FIX_CONFIDENCE_VERSION,
        "quality_gate_version": QUALITY_GATE_VERSION,
        "review_evidence_calibration_version": CALIBRATION_VERSION,
        "image_alt_evidence_version": IMAGE_ALT_EVIDENCE_VERSION,
        "indexability_quality_version": INDEXABILITY_QUALITY_VERSION,
        "navigation_indexability_version": NAVIGATION_INDEXABILITY_VERSION,
        "metadata_evidence_version": METADATA_EVIDENCE_VERSION,
        "title_evidence_version": TITLE_EVIDENCE_VERSION,
        "page_evidence_gate_version": PAGE_EVIDENCE_GATE_VERSION,
        "render_evidence_quality_version": RENDER_EVIDENCE_QUALITY_VERSION,
        "trust_discovery_version": TRUST_DISCOVERY_VERSION,
        "trust_finding_gate_version": TRUST_FINDING_GATE_VERSION,
        "crawler_acceptance_version": CRAWLER_ACCEPTANCE_VERSION,
        "evidence_quality_gate_version": EVIDENCE_QUALITY_GATE_VERSION,
        "coverage_authority_evidence_version": COVERAGE_AUTHORITY_EVIDENCE_VERSION,
        "frontier_policy_version": FRONTIER_POLICY_VERSION,
    }

    # Cross-runtime markers participate in the same fingerprint, so a
    # Base44/frontend behavior change cannot ship under an unchanged release
    # identity. A collision would silently let one runtime redefine another's
    # marker, so it fails closed rather than being merged.
    for key, value in load_cross_runtime_components().items():
        if key in components:
            raise RuntimeError(f"Cross-runtime component {key!r} collides with a Python component.")
        components[key] = value
    return components


def fingerprint(component_versions: dict[str, str]) -> str:
    """Stable short hash over the version set; order-independent."""
    payload = json.dumps(component_versions, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def live_revision() -> dict[str, Any]:
    """The revision fingerprint of the code that is running right now."""
    components = collect_component_versions()
    return {
        "schema_version": BETA_REVISION_SCHEMA_VERSION,
        "component_versions": components,
        "fingerprint": fingerprint(components),
    }


def load_recorded_revision(path: Path | str | None = None) -> dict[str, Any]:
    """Load the committed frozen-revision record."""
    target = Path(path) if path else DEFAULT_REVISION_PATH
    with target.open(encoding="utf-8") as handle:
        return json.load(handle)


def diff_versions(recorded: dict[str, Any], live: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Per-component drift between a recorded revision and a live one.

    Empty dict means the live code matches the frozen promise.
    """
    recorded_components = dict(recorded.get("component_versions") or {})
    live_components = dict(live.get("component_versions") or {})
    drift: dict[str, dict[str, Any]] = {}
    for key in sorted(set(recorded_components) | set(live_components)):
        recorded_value = recorded_components.get(key)
        live_value = live_components.get(key)
        if recorded_value != live_value:
            drift[key] = {"recorded": recorded_value, "live": live_value}
    return drift


def build_revision_record(
    *,
    git_commit: str = "",
    recorded_at: str = "",
    acceptance_report: str = "",
    note: str = "",
) -> dict[str, Any]:
    """Assemble a frozen-revision record from live versions plus provenance."""
    revision = live_revision()
    # A record is only frozen once it names the exact deployed commit AND the
    # acceptance report that accepted it. Recording an unaccepted candidate as
    # `frozen_beta` would let release tooling and reviewers read a promise that
    # production never made.
    accepted = bool(str(git_commit).strip()) and bool(str(acceptance_report).strip())
    return {
        "schema_version": BETA_REVISION_SCHEMA_VERSION,
        "status": "frozen_beta" if accepted else "candidate",
        "git_commit": git_commit,
        "recorded_at": recorded_at,
        "acceptance_report": acceptance_report,
        "note": note,
        "fingerprint": revision["fingerprint"],
        "component_versions": revision["component_versions"],
    }
