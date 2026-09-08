from __future__ import annotations

from typing import Any, Mapping

CURRENT_TOP_LEVEL_FIELDS = frozenset(
    {
        "release_gate_eligible",
        "scan_id",
        "project_id",
        "website_url",
        "normalized_domain",
        "beta_revision_fingerprint",
        "scanner_version",
        "scanner_build_revision",
        "review_version",
        "scan_status",
        "health_score",
        "health_grade",
        "pages_found",
        "pages_crawled",
        "customer_summary",
        "next_best_step",
        "project",
        "fix_list",
        "recommendations",
    }
)

CURRENT_RECOMMENDATION_FIELDS = frozenset(
    {
        "fix_id",
        "rule",
        "category",
        "issue_title",
        "plain_english_explanation",
        "why_it_matters",
        "current_value",
        "recommended_value",
        "simple_next_step",
        "priority",
        "difficulty",
        "requires_developer",
        "requires_approval",
        "user_status",
        "page_url",
        "affected_pages",
        "source_pages",
        "what_to_do_steps",
        "verified_urls",
    }
)

CANONICAL_V2_FIELDS_NOT_CURRENTLY_SENT = frozenset(
    {
        "action_priority",
        "action_priority_score",
        "canonical_action_rank",
        "priority_context",
        "repair_contract_version",
        "repair_fingerprint",
        "repair_identity_state",
        "repair_identity_stable",
        "repair_identity_version",
        "repair_priority_model_version",
        "repair_snapshot_contract_version",
    }
)


def validate_provider_payload(evidence: Mapping[str, Any]) -> None:
    """Validate the current model-facing evidence shape without inventing authority.

    The authority manifest is validated separately. This function only confirms
    that a fixture represents the compact payload currently sent to `/chat`.
    """

    if evidence.get("release_gate_eligible") is not True:
        raise ValueError("provider payload must have release_gate_eligible=true.")
    for required in ("scan_id", "project_id", "normalized_domain"):
        if not str(evidence.get(required) or "").strip():
            raise ValueError(f"provider payload must include {required}.")
    recommendations = evidence.get("recommendations")
    if not isinstance(recommendations, list):
        raise ValueError("provider payload recommendations must be a list.")
    for index, item in enumerate(recommendations):
        if not isinstance(item, Mapping):
            raise ValueError(f"recommendation {index} must be an object.")
        if not str(item.get("fix_id") or "").strip():
            raise ValueError(f"recommendation {index} must include fix_id.")
        leaked = CANONICAL_V2_FIELDS_NOT_CURRENTLY_SENT.intersection(item.keys())
        if leaked:
            raise ValueError(
                "fixture does not match the current provider payload; canonical v2 fields are present: "
                + ", ".join(sorted(leaked))
            )
