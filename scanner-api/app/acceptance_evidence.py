"""Measured Standard 150 release-acceptance evidence.

The ramp harness must consume observations produced by the real worker and
bound into durable result integrity.  This module owns the two observations
that are not already native ScanRun fields: the reviewed classification verdict
and the Cloud Run worker's process peak memory.
"""

from __future__ import annotations

import resource
import sys
from collections.abc import Callable
from typing import Any


ACCEPTANCE_EVIDENCE_VERSION = "standard150_acceptance_evidence_v1"


def build_classification_integrity(review: dict[str, Any]) -> dict[str, Any]:
    """Return the reviewed classifier verdict without inferring from its label."""
    fingerprint = review.get("site_fingerprint") if isinstance(review, dict) else None
    fingerprint = fingerprint if isinstance(fingerprint, dict) else {}
    classification = fingerprint.get("classification")
    classification = classification if isinstance(classification, dict) else {}
    state = str(classification.get("state") or fingerprint.get("classification_state") or "").strip()
    if not state:
        return {}

    usable_pages = classification.get("usable_pages")
    usable_pages = (
        max(0, int(usable_pages))
        if isinstance(usable_pages, (int, float)) and not isinstance(usable_pages, bool)
        else 0
    )
    return {
        "version": ACCEPTANCE_EVIDENCE_VERSION,
        "state": state[:120],
        "verdict": state[:120],
        "classifier_version": str(
            review.get("archetype_classifier_version")
            or classification.get("classifier_version")
            or ""
        ).strip()[:160],
        "evidence_sufficiency": str(classification.get("evidence_sufficiency") or "").strip()[:120],
        "usable_pages": usable_pages,
        "complete_small_site_inventory": classification.get("complete_small_site_inventory") is True,
    }


def measure_worker_peak_memory_bytes(
    *,
    getrusage: Callable[[int], Any] = resource.getrusage,
    self_target: int = resource.RUSAGE_SELF,
    children_target: int = resource.RUSAGE_CHILDREN,
    platform: str = sys.platform,
) -> int | None:
    """Measure the larger worker/review-child maximum resident set size.

    Cloud Run is Linux and reports ``ru_maxrss`` in KiB.  macOS reports bytes;
    accepting the platform explicitly keeps the conversion testable.  The
    durable worker deploy is concurrency=1, so the process peak is a truthful,
    conservative resource observation for the active scan.
    """
    try:
        peak = max(
            float(getrusage(self_target).ru_maxrss),
            float(getrusage(children_target).ru_maxrss),
        )
    except (AttributeError, OSError, TypeError, ValueError):
        return None
    if peak <= 0:
        return None
    multiplier = 1 if platform == "darwin" else 1024
    measured = int(peak * multiplier)
    return measured if measured > 0 else None
