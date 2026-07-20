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
from pathlib import Path
from typing import Any

BETA_REVISION_SCHEMA_VERSION = "beta_crawler_revision_v1"

# Repo-root/data/beta-crawler-revision.json, resolved from this file's location
# (app/ -> scanner-api/ -> repo root).
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REVISION_PATH = REPO_ROOT / "data" / "beta-crawler-revision.json"


def collect_component_versions() -> dict[str, str]:
    """Read the authoritative version constants live from the scanner modules.

    Imports are local so freeze tooling can call this without constructing the
    FastAPI app or paying for heavier imports at module load time.
    """
    from .artifact_filter import ARTIFACT_FILTER_VERSION
    from .crawler_acceptance import CRAWLER_ACCEPTANCE_VERSION
    from .indexability_quality import INDEXABILITY_QUALITY_VERSION
    from .navigation_indexability import NAVIGATION_INDEXABILITY_VERSION
    from .metadata_title_evidence import METADATA_EVIDENCE_VERSION, TITLE_EVIDENCE_VERSION
    from .page_evidence_gate import PAGE_EVIDENCE_GATE_VERSION
    from .redirect_validation import REDIRECT_EVIDENCE_VERSION
    from .render_evidence_quality import RENDER_EVIDENCE_QUALITY_VERSION
    from .render_followup import RENDER_FOLLOWUP_VERSION
    from .review import (
        ARCHETYPE_CLASSIFIER_VERSION,
        ORPHAN_ASSET_EVIDENCE_VERSION,
        PAGE_LEVEL_ASSET_EVIDENCE_VERSION,
        REPRESENTATIVE_PAGE_VERSION,
        QUALITY_GATE_VERSION,
        REVIEW_VERSION,
        ZERO_FIX_CONFIDENCE_VERSION,
    )
    from .review_calibration import CALIBRATION_VERSION, IMAGE_ALT_EVIDENCE_VERSION
    from .sampling import SAMPLING_VERSION
    from .scanner import RENDER_EVIDENCE_VERSION, VERSION
    from .trust_discovery import TRUST_DISCOVERY_VERSION, TRUST_FINDING_GATE_VERSION

    return {
        "scanner_version": VERSION,
        "artifact_filter_version": ARTIFACT_FILTER_VERSION,
        "redirect_evidence_version": REDIRECT_EVIDENCE_VERSION,
        "render_evidence_version": RENDER_EVIDENCE_VERSION,
        "sampling_version": SAMPLING_VERSION,
        "render_followup_version": RENDER_FOLLOWUP_VERSION,
        "review_version": REVIEW_VERSION,
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
    }


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
    return {
        "schema_version": BETA_REVISION_SCHEMA_VERSION,
        "status": "frozen_beta",
        "git_commit": git_commit,
        "recorded_at": recorded_at,
        "acceptance_report": acceptance_report,
        "note": note,
        "fingerprint": revision["fingerprint"],
        "component_versions": revision["component_versions"],
    }
