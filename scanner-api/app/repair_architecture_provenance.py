"""Conservative, scanner-owned architecture provenance for shadow repair ranking.

Only prevalidated, scanner-generated claims may promote or demote a template.
Never populate these claims directly from HTML, LLM text, or user-supplied input.
A recognized label alone does not establish evidence: every claim also needs
producer, evidence_id, and verified=True. This is a *shadow* contract; there is
no production producer/activation in this change.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit

from .repair_coverage import evidence_url_key

ARCHITECTURE_ROLE_EVIDENCE_VERSION = "architecture_role_evidence_v1"

# A source can attest to exactly one kind of claim. Arbitrary claimed role
# strings cannot override the scanner's existing template classification.
_VERIFIED_SOURCES = {
    "verified_taxonomy": "structural",
    "verified_directory": "structural",
    "verified_product_gateway": "structural",
    "verified_customer_journey": "business_critical",
    "verified_promotional_surface": "support",
    "verified_entity_listing": "commercial_leaf",
}

LEAF_SCOPES = frozenset({
    "seller_profile", "provider_profile", "seller_detail", "provider_detail",
    "seller_offer", "provider_offer", "product_offer", "profile", "offer",
})
LEAF_FAMILIES = frozenset({
    "seller_profile", "provider_profile", "seller_detail", "provider_detail",
    "seller_offer", "provider_offer", "product_offer",
})
DIRECTORY_FAMILIES = frozenset({"seller_directory", "provider_directory"})


def provenance_decision(page: dict[str, Any], *, authenticated_producer: bool = False) -> tuple[str, str | None]:
    """Return (state, trusted role override); fail closed without authenticated source.

    authenticated_producer is a caller-side authority decision, never a field
    on the page, website payload, source claim, or persisted customer record.
    Production deliberately does not pass this override until a trusted
    scanner-side producer is implemented and end-to-end tested.
    """
    evidence = page.get("architecture_role_evidence")
    if evidence is None:
        return "template_only", None
    if not isinstance(evidence, dict):
        return "insufficient_evidence", None
    if evidence.get("version") != ARCHITECTURE_ROLE_EVIDENCE_VERSION:
        return "insufficient_evidence", None
    claims = evidence.get("claims")
    if not isinstance(claims, list) or not claims:
        return "insufficient_evidence", None

    # The producer/source/verified fields are merely self-reported JSON. Until
    # a trusted scanner-side producer/verification boundary explicitly supplies
    # authenticated_producer=True, no claim may influence customer ranking.
    # In particular, a remote site can never self-attest this boolean.
    if authenticated_producer is not True:
        return "insufficient_evidence", None

    roles: set[str] = set()
    for claim in claims:
        if not isinstance(claim, dict):
            return "insufficient_evidence", None
        source = claim.get("source")
        role = claim.get("role")
        ref = claim.get("evidence_id")
        if (
            claim.get("producer") != "fixlist_scanner_verified"
            or claim.get("verified") is not True
            or not isinstance(ref, str)
            or not ref.strip()
            or _VERIFIED_SOURCES.get(source) != role
        ):
            return "insufficient_evidence", None
        roles.add(role)

    if len(roles) != 1:
        return "conflicted", None
    role = next(iter(roles))
    state = {
        "structural": "proven_structural",
        "business_critical": "proven_business_critical",
        "commercial_leaf": "template_only",
        "support": "promotional_or_transient",
    }[role]
    return state, role


def is_repeated_entity_leaf(page: dict[str, Any]) -> bool:
    scope = str(page.get("entity_scope") or "").strip().lower()
    family = str(page.get("page_template_family") or page.get("template_family") or "").strip().lower()
    return scope in LEAF_SCOPES or family in LEAF_FAMILIES


def strip_acquisition_utm(value: Any) -> str:
    """Discard any utm_* (including custom keys), while preserving other query."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlsplit(raw)
    kept = [
        part for part in parsed.query.split("&")
        if part and not unquote(part.partition("=")[0]).lower().startswith("utm_")
    ]
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "&".join(kept), ""))


def architectural_evidence_key(value: Any) -> str:
    """Reuse cross-product evidence identity; preserve substantive query state."""
    return evidence_url_key(strip_acquisition_utm(value))
