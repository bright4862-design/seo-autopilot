"""Measured Standard 150 release-acceptance evidence.

The ramp harness must consume observations produced by the real worker and
bound into durable result integrity.  This module owns the two observations
that are not already native ScanRun fields: the reviewed classification verdict
and the Cloud Run worker's process peak memory.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any


ACCEPTANCE_EVIDENCE_VERSION = "standard150_acceptance_evidence_v2_aggregate_rss_fail_closed"


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


def _linux_process_rss_bytes(pid: int) -> int | None:
    """Return one process's current RSS from Linux /proc, or None if unknown."""
    try:
        status = Path(f"/proc/{int(pid)}/status").read_text(encoding="utf-8")
    except (OSError, TypeError, ValueError):
        return None
    for line in status.splitlines():
        if not line.startswith("VmRSS:"):
            continue
        parts = line.split()
        if len(parts) < 2:
            return None
        try:
            kib = int(parts[1])
        except ValueError:
            return None
        return kib * 1024 if kib > 0 else None
    return None


def measure_worker_peak_memory_bytes(
    *,
    child_pid: int | None = None,
    rss_reader: Callable[[int], int | None] = _linux_process_rss_bytes,
    self_pid: int | None = None,
    platform: str = sys.platform,
) -> int | None:
    """Sample aggregate worker + active review-child RSS for one scan.

    Cloud Run is Linux.  The caller owns peak tracking and invokes this while
    the isolated review child is alive, so each review starts from a fresh local
    maximum and cannot inherit a terminated child's prior peak.
    """
    if not str(platform).startswith("linux"):
        return None
    parent_pid = int(self_pid or os.getpid())
    try:
        parent_rss = rss_reader(parent_pid)
        child_rss = rss_reader(int(child_pid)) if child_pid is not None else 0
    except (OSError, TypeError, ValueError):
        return None
    if parent_rss is None or parent_rss <= 0:
        return None
    if child_pid is not None and (child_rss is None or child_rss <= 0):
        return None
    measured = int(parent_rss + (child_rss or 0))
    return measured if measured > 0 else None
