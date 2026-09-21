"""Fail-closed projections for internal Stage-2 page evidence.

Stage-2 producers retain richer evidence long enough for deterministic review and
scan-level aggregation. Those intermediate fields are not part of the approved
HTTP/customer/persistence contract. The common post-crawl boundary projects page
records through this module instead of forwarding producer dictionaries.
"""
from __future__ import annotations

from typing import Any, Iterable


INTERNAL_PAGE_EVIDENCE_FIELDS = frozenset({
    # B10 deterministic main-content intermediate evidence.
    "main_text",
    "main_text_evidence_version",
    "main_text_signature",
    "main_text_representation",
    "main_text_token_count",
    "main_text_char_count",
    "main_text_source",
    "main_text_verified",
    "main_text_reason",
    "main_text_truncated",
    # B13/B14 extraction intermediates. The scan-level aggregate is reduced to
    # non-content states/counts before persistence; raw normalized observations
    # are deliberately not a customer/persistence page field.
    "local_entity_observations",
    "location_context",
    # B15 evidence remains internal until an authenticated customer contract is
    # intentionally added.
    "contextual_freshness_evidence",
    # B11's private retained-link cache should already be removed by the
    # producer. Keeping it documented here makes the privacy classification
    # explicit even though the external projector is now a positive allowlist.
    "_reachability_links",
})

# External page records are a contract, not a copy of whatever a producer learns
# next. Keep the current public/authority fields explicit so a future debug or
# evidence field cannot cross HTTP, signing, persistence, preview, or export
# boundaries merely because its name was not added to a deny-list.
_EXTERNAL_PAGE_ALLOWED_FIELDS = frozenset({
    # Route/request identity and crawl provenance.
    "url",
    "requested_url",
    "page_url",
    "final_url",
    "verified_final_url",
    "path",
    "status_code",
    "http_status",
    "response_status",
    "fetch_error",
    "content_type",
    "raw_html_truncated",
    "html_truncated",
    "page_evidence_class",
    "evidence_gate_version",
    "discovered_from",
    "source_pages",
    "link_text_samples",
    "url_confidence",
    "url_suspicion_reasons",
    "route_boundary_candidate",
    "route_boundary_type",
    "url_verification",
    "evidence_url_identity_version",
    "trust_discovery_probe",

    # Search metadata and accepted Stage-1 content evidence.
    "title",
    "title_pixel_width_estimate",
    "title_width_state",
    "title_is_generic_fallback",
    "title_evidence_version",
    "meta_description",
    "meta_description_state",
    "meta_description_element_count",
    "meta_description_values",
    "meta_description_duplicate",
    "metadata_evidence_version",
    "h1",
    "h1_count",
    "word_count",
    "html_size",
    "image_count",
    "image_missing_alt_count",
    "missing_alt_image_count",
    "image_alt_applicability",
    "visible_template_evidence",
    "template_content_issue_types",
    "template_content_issue_count",
    "template_content_issue_evidence",
    "schema_types",
    "has_schema",
    "page_template_family",
    "estimated_page_intent",

    # B17 weight evidence is scalar and explicitly approved for the external
    # result. B10 fingerprints are intentionally absent from this allowlist.
    "page_weight_evidence_version",
    "decoded_bytes",
    "decoded_bytes_basis",
    "inline_script_bytes",
    "inline_style_bytes",
    "transfer_bytes",
    "transfer_bytes_state",
    "transfer_bytes_basis",
    "response_body_bytes",

    # Indexability, robots, canonical, URL-quality, and search applicability.
    "canonical",
    "canonical_url",
    "canonical_href_resolution_version",
    "canonical_status",
    "canonical_target_validation_version",
    "canonical_target_url",
    "canonical_target_state",
    "canonical_target_status_code",
    "canonical_target_indexability_state",
    "canonical_target_fetch_error",
    "canonical_target_redirect_location",
    "canonical_target_declared_canonical",
    "canonical_target_evidence_source",
    "canonical_target_checked",
    "canonical_origin_alias",
    "canonical_origin_alias_source_url",
    "canonical_origin_alias_target_url",
    "robots",
    "robots_meta",
    "robots_meta_directives",
    "googlebot_robots",
    "crawler_specific_robots",
    "x_robots_tag",
    "x_robots_tag_directives",
    "effective_search_robots_directives",
    "robots_indexability_status",
    "robots_txt_url",
    "robots_txt_status",
    "robots_txt_status_code",
    "robots_txt_rules_known",
    "robots_txt_scanner_allowed",
    "robots_txt_googlebot_allowed",
    "robots_txt_oai_searchbot_allowed",
    "robots_txt_scanner_blocked",
    "robots_txt_googlebot_blocked",
    "robots_txt_owner_override_applied",
    "robots_txt_fetch_allowed",
    "indexable",
    "indexability_state",
    "indexability_quality_version",
    "indexability_state_before_quality",
    "canonicalized_by_valid_target",
    "indexability_conflicts",
    "indexability_conflict_signals",
    "soft_404_suspected",
    "soft_404_signals",
    "soft_404_confidence",
    "search_applicability",

    # Access limitation evidence is bounded by page_evidence_gate.py.
    "access_block_vendor",
    "access_block_kind",
    "access_block_signal",
    "access_block_headers",

    # Redirect evidence and meaning are already bounded/versioned customer
    # diagnostics. Raw HTML and transient transport objects are not included.
    "redirect_evidence_version",
    "redirect_state",
    "redirect_outcome",
    "redirect_fetch_evidence",
    "redirect_source_url",
    "redirect_source_path",
    "redirect_hop_count",
    "redirect_hops",
    "redirect_chain",
    "redirect_destination_url",
    "redirect_destination_status_code",
    "redirect_destination_indexability_state",
    "redirect_destination_indexable",
    "redirect_destination_googlebot_blocked",
    "redirect_destination_scanner_blocked",
    "redirect_fetch_error",
    "redirect_chain_truncated",
    "origin_alias_redirect",
    "origin_alias_redirect_hop_count",
    "origin_alias_redirect_chain",
    "origin_alias_destination_url",
    "origin_alias_destination_indexability_state",

    # Navigation/indexability diagnostics.
    "navigation_indexability_version",
    "navigation_query_keys",
    "pagination_query_keys",
    "facet_query_keys",
    "pagination_url",
    "faceted_navigation_url",
    "tracking_only_url",
    "orphan_evidence_state",
    "potential_orphan_in_sample",
    "indexable_faceted_url",

    # B11 retained-sample reachability is intentionally scoped and safe; raw
    # outgoing-link observations (`_reachability_links`) remain private.
    "reachability_provenance_version",
    "reachability_scope",
    "reachability_evidence_state",
    "observed_internal_inlink_count",
    "internal_source_pages",
    "internal_source_pages_truncated",
    "navigation_presence",
    "navigation_source_pages",
    "crawl_depth",
    "sitewide_orphan_claim",

    # Existing authenticated GEO page evidence and its compatibility metadata.
    "geo_evidence",
    "geo_evidence_error",
    "geo_scope",
    "geo_scope_reason",
    "geo_search_intent",
    "geo_evidence_version",
    "geo_applicability",
    "geo_applicability_reason",
    "geo_content_digest",

    # Client-rendering observations are bounded scalar/list diagnostics.
    "client_rendering_suspected",
    "client_rendering_signals",
})

PAGE_LIST_KEYS = ("pages", "crawled_pages", "scanned_pages", "crawl_pages")

_LOCAL_ENTITY_AGGREGATE_ALLOWED_FIELDS = frozenset({
    "producer_version",
    "context_provenance_version",
    "local_entity_version",
    "nap_consistency_version",
    "eligible_observations",
    "selected_observations",
    "selection_truncated",
})

_LOCAL_COMPLETENESS_ALLOWED_FIELDS = frozenset({
    "version",
    "state",
    "reason",
    "missing_required",
    "unverified_fields",
    "contextual_status",
    "optional_available",
    "entity_match",
    "entity_identity_reason",
    "source",
    "surface_provenance",
    "context_provenance_version",
    "contextual_status_state",
})

_LOCAL_NAP_ALLOWED_FIELDS = frozenset({
    "version",
    "state",
    "verified_observations",
    "ambiguous_observations",
    "comparable_entity_groups",
    "unverified_entity_groups",
    "scope",
    "sitewide_consistency_claim",
})

_LOCAL_NAP_INCONSISTENCY_ALLOWED_FIELDS = frozenset({
    "fields",
    "source_count",
    "provenance",
})


def project_page_for_external_boundary(page: Any) -> Any:
    """Copy only explicitly approved fields from one external page record.

    Unknown fields fail closed by default. Adding a new producer/debug field
    therefore cannot silently expand the signed/customer page contract; a future
    externally required field must be reviewed and deliberately classified here.
    """
    if not isinstance(page, dict):
        return page
    return {
        key: value
        for key, value in page.items()
        if key in _EXTERNAL_PAGE_ALLOWED_FIELDS
    }


def project_pages_for_external_boundary(pages: Iterable[Any]) -> list[Any]:
    """Return a projected page list without mutating internal review evidence."""
    return [project_page_for_external_boundary(page) for page in pages]


def project_local_entity_scan_evidence(evidence: Any) -> Any:
    """Keep only approved B13/B14 states/counts at the external boundary.

    The producer aggregate is useful downstream for requirement/version/state
    proof, but its internal rows still carry exact page URLs, absolute entity IDs
    and accepted-heading provenance. Use positive allowlists at every aggregate
    level so a future producer/debug field cannot silently become customer or
    persisted output merely because the producer learned a new shape.
    """
    if not isinstance(evidence, dict):
        return evidence

    projected = {
        key: value
        for key, value in evidence.items()
        if key in _LOCAL_ENTITY_AGGREGATE_ALLOWED_FIELDS
    }

    completeness = evidence.get("completeness")
    if isinstance(completeness, list):
        projected["completeness"] = [
            {
                key: value
                for key, value in row.items()
                if key in _LOCAL_COMPLETENESS_ALLOWED_FIELDS
            }
            for row in completeness
            if isinstance(row, dict)
        ]

    nap = evidence.get("nap_consistency")
    if isinstance(nap, dict):
        safe_nap = {
            key: value
            for key, value in nap.items()
            if key in _LOCAL_NAP_ALLOWED_FIELDS
        }
        inconsistencies = nap.get("inconsistencies")
        if isinstance(inconsistencies, list):
            safe_nap["inconsistencies"] = [
                {
                    key: value
                    for key, value in row.items()
                    if key in _LOCAL_NAP_INCONSISTENCY_ALLOWED_FIELDS
                }
                for row in inconsistencies
                if isinstance(row, dict)
            ]
        projected["nap_consistency"] = safe_nap

    return projected


def _project_local_entity_aggregate(container: dict[str, Any]) -> dict[str, Any]:
    projected = dict(container)
    if "local_entity_scan_evidence" in container:
        projected["local_entity_scan_evidence"] = project_local_entity_scan_evidence(
            container.get("local_entity_scan_evidence")
        )
    return projected


def project_scan_result_for_external_boundary(result: dict[str, Any]) -> dict[str, Any]:
    """Copy a scan while removing producer-only content/identity evidence.

    Page arrays are projected independently so aliases cannot retain a private
    or unknown future field. B13/B14 scan-level evidence is reduced to versioned
    states/counts and non-content diagnostics. The input result is never mutated.
    """
    projected = _project_local_entity_aggregate(result)
    for key in PAGE_LIST_KEYS:
        value = result.get(key)
        if isinstance(value, list):
            projected[key] = project_pages_for_external_boundary(value)

    technical = result.get("technical_audit_summary")
    if isinstance(technical, dict):
        projected["technical_audit_summary"] = _project_local_entity_aggregate(technical)

    return projected
