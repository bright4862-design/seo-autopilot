"""Context-qualified local location-shell evidence for Stage 2 B13.

This module consumes already-accepted page/template observations only. It does
not fetch, render, infer business status, or turn failed rendering into a defect.
"""
from __future__ import annotations

import re
from typing import Any

LOCAL_SHELL_VERSION = "local_shell_context_v1"
PREOPEN_STATUSES = {"coming_soon", "preopening", "pre_opening", "opening_soon"}
OPEN_STATUSES = {"open", "active", "operating"}
SHELL_TYPES = {"empty_shell", "coming_soon_shell"}


def _status(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def assess_local_shell(observation: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a local-page shell only when applicability and raw evidence are explicit."""
    if not isinstance(observation, dict):
        raise ValueError("Expected local shell observation")
    applicable = observation.get("applicable")
    if applicable is False:
        return {
            "version": LOCAL_SHELL_VERSION,
            "state": "not_applicable",
            "reason": "not_a_local_entity_page",
            "contextual_status": None,
            "shell_issue_types": [],
        }
    if applicable is not True:
        return {
            "version": LOCAL_SHELL_VERSION,
            "state": "not_verified",
            "reason": "local_page_applicability_unknown",
            "contextual_status": None,
            "shell_issue_types": [],
        }
    if (
        observation.get("accepted") is not True
        or observation.get("page_evidence_class") != "usable_html"
        or observation.get("client_rendering_suspected") is True
        or observation.get("rendering_failed") is True
    ):
        return {
            "version": LOCAL_SHELL_VERSION,
            "state": "not_verified",
            "reason": "accepted_local_shell_evidence_unavailable",
            "contextual_status": _status(observation.get("contextual_status")) or None,
            "shell_issue_types": [],
        }

    template = observation.get("visible_template_evidence")
    if not isinstance(template, dict) or template.get("accepted") is not True:
        return {
            "version": LOCAL_SHELL_VERSION,
            "state": "not_verified",
            "reason": "visible_template_evidence_unavailable",
            "contextual_status": _status(observation.get("contextual_status")) or None,
            "shell_issue_types": [],
        }
    issue_types = sorted(
        SHELL_TYPES.intersection(
            value for value in template.get("issue_types", []) if isinstance(value, str)
        )
    )
    status = _status(observation.get("contextual_status"))
    if "empty_shell" in issue_types:
        return {
            "version": LOCAL_SHELL_VERSION,
            "state": "fail",
            "reason": "empty_local_content_shell",
            "contextual_status": status or None,
            "shell_issue_types": issue_types,
        }
    if "coming_soon_shell" in issue_types:
        if status in PREOPEN_STATUSES:
            return {
                "version": LOCAL_SHELL_VERSION,
                "state": "pass",
                "reason": "coming_soon_shell_matches_contextual_status",
                "contextual_status": status,
                "shell_issue_types": issue_types,
            }
        if status in OPEN_STATUSES:
            return {
                "version": LOCAL_SHELL_VERSION,
                "state": "fail",
                "reason": "coming_soon_shell_conflicts_with_open_status",
                "contextual_status": status,
                "shell_issue_types": issue_types,
            }
        return {
            "version": LOCAL_SHELL_VERSION,
            "state": "not_verified",
            "reason": "coming_soon_shell_status_unverified",
            "contextual_status": status or None,
            "shell_issue_types": issue_types,
        }
    return {
        "version": LOCAL_SHELL_VERSION,
        "state": "pass",
        "reason": "no_local_shell_condition_observed",
        "contextual_status": status or None,
        "shell_issue_types": [],
    }
