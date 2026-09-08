from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from .page_evidence_gate import page_has_usable_html


TEMPLATE_CONTENT_EVIDENCE_LIMIT = 4
_LOCATION_TOKEN_NAMES = "location|city|state|region|market|area"
UNRESOLVED_LOCATION_TOKEN_RE = re.compile(
    rf"(?:#(?:{_LOCATION_TOKEN_NAMES})#|"
    rf"\{{var[-_](?:{_LOCATION_TOKEN_NAMES})\}}|"
    rf"\{{\{{\s*(?:{_LOCATION_TOKEN_NAMES})\s*\}}\}}|"
    rf"\$\{{\s*(?:{_LOCATION_TOKEN_NAMES})\s*\}})",
    re.I,
)

# Generic placeholder detection deliberately stays narrower than a template
# parser. These signatures must be visible in rendered page text and strongly
# resemble unfinished customer copy. Bare "XX" and one literal "gvar" are not
# enough evidence on their own.
_GENERIC_TOKEN_NAMES = (
    "location|city|state|region|market|area|product|service|company|brand|"
    "phone|email|url|name|title"
)
UNRESOLVED_GENERIC_VARIABLE_RE = re.compile(
    rf"(?:#(?:{_GENERIC_TOKEN_NAMES})#|"
    rf"\{{var[-_](?:{_GENERIC_TOKEN_NAMES})\}}|"
    rf"\{{\{{\s*(?:{_GENERIC_TOKEN_NAMES})\s*\}}\}}|"
    rf"\$\{{\s*(?:{_GENERIC_TOKEN_NAMES})\s*\}})",
    re.I,
)
GLOBAL_VARIABLE_PLACEHOLDER_RE = re.compile(r"(?<![A-Za-z0-9_])gvar\+(?![A-Za-z0-9_])", re.I)
CONTEXTUAL_XX_PLACEHOLDER_RE = re.compile(
    r"\b(?:visit|view|see|explore|open|check)\s+(?:(?:our|the|this)\s+)?XX\s+(?:page|section)\b",
    re.I,
)
GENERIC_PLACEHOLDER_ISSUE_TYPES = {
    "global_variable_placeholder",
    "contextual_xx_placeholder",
    "delimited_template_variable",
}
LOCATION_TEMPLATE_ISSUE_TYPES = {
    "unresolved_location_token",
    "wrong_location_copy",
}
# Start with customer-facing commercial surfaces where unfinished template text
# is very unlikely to be an intentional code example. Editorial/article and
# account/archive surfaces are excluded even if extraction observes the syntax.
GENERIC_PLACEHOLDER_REPAIR_FAMILIES = {
    "homepage",
    "activity_detail",
    "booking_or_checkout",
    "calculator",
    "collection_page",
    "comparison_page",
    "contact",
    "conversion",
    "loan_program",
    "product_page",
}

US_STATE_NAMES = (
    "Alabama",
    "Alaska",
    "Arizona",
    "Arkansas",
    "California",
    "Colorado",
    "Connecticut",
    "Delaware",
    "District of Columbia",
    "Florida",
    "Georgia",
    "Hawaii",
    "Idaho",
    "Illinois",
    "Indiana",
    "Iowa",
    "Kansas",
    "Kentucky",
    "Louisiana",
    "Maine",
    "Maryland",
    "Massachusetts",
    "Michigan",
    "Minnesota",
    "Mississippi",
    "Missouri",
    "Montana",
    "Nebraska",
    "Nevada",
    "New Hampshire",
    "New Jersey",
    "New Mexico",
    "New York",
    "North Carolina",
    "North Dakota",
    "Ohio",
    "Oklahoma",
    "Oregon",
    "Pennsylvania",
    "Rhode Island",
    "South Carolina",
    "South Dakota",
    "Tennessee",
    "Texas",
    "Utah",
    "Vermont",
    "Virginia",
    "Washington",
    "West Virginia",
    "Wisconsin",
    "Wyoming",
)
STATE_BY_SLUG = {
    re.sub(r"[^a-z0-9]+", "-", state.lower()).strip("-"): state
    for state in US_STATE_NAMES
}
STATE_BY_SLUG["washington-dc"] = "District of Columbia"
STATE_BY_SLUG["dc"] = "District of Columbia"
_STATE_ALTERNATION = "|".join(
    re.escape(state) for state in sorted(US_STATE_NAMES, key=len, reverse=True)
)
STATE_LENDER_PHRASE_RE = re.compile(
    rf"\b(?P<state>{_STATE_ALTERNATION})\s+"
    r"(?:(?:hard|private)\s+money\s+)?lenders?\b",
    re.I,
)
STRONG_WRONG_LOCATION_COPY_RE = re.compile(
    r"\b(?:as|we(?:\s+are|'re)|our\s+(?:team|company)\s+(?:is|are))\s+"
    rf"(?P<state>{_STATE_ALTERNATION})\s+"
    r"(?:(?:hard|private)\s+money\s+)?lenders?\b",
    re.I,
)


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _location_slug_from_path(path: str) -> str:
    """Return one explicit /locations/<market> slug, or empty outside that surface."""
    clean_path = urlparse(str(path or "")).path.lower().rstrip("/")
    match = re.search(r"(?:^|/)locations/([^/?#]+)$", clean_path)
    return match.group(1).strip("/") if match else ""


def _location_state_from_path(path: str) -> str:
    return STATE_BY_SLUG.get(_location_slug_from_path(path), "")


def _evidence_snippet(text: str, start: int, end: int, radius: int = 72) -> str:
    source = str(text or "")
    left = max(0, int(start) - radius)
    right = min(len(source), int(end) + radius)
    snippet = _clean_text(source[left:right])
    if left > 0:
        snippet = f"…{snippet}"
    if right < len(source):
        snippet = f"{snippet}…"
    return snippet[:260]


def _overlaps(span: tuple[int, int], others: list[tuple[int, int]]) -> bool:
    start, end = span
    return any(start < other_end and end > other_start for other_start, other_end in others)


def _record_match(
    source: str,
    match: re.Match[str],
    issue_type: str,
    issue_types: list[str],
    evidence: list[str],
) -> None:
    if issue_type not in issue_types:
        issue_types.append(issue_type)
    snippet = _evidence_snippet(source, match.start(), match.end())
    if snippet and snippet not in evidence and len(evidence) < TEMPLATE_CONTENT_EVIDENCE_LIMIT:
        evidence.append(snippet)


def detect_location_template_content(
    path: str,
    title: str,
    h1: str,
    visible_text: str,
) -> dict[str, Any]:
    """Return bounded visible broken-template evidence.

    Location-specific checks retain their existing narrow URL/evidence rules.
    Generic placeholder checks run on visible text only and do not themselves
    claim that different pages share one implementation component.
    """
    location_slug = _location_slug_from_path(path)

    # extract.py's visible_text already contains the document title and headings.
    # Scan that source once so placeholder counts and evidence are not duplicated.
    source = _clean_text(visible_text)
    issue_types: list[str] = []
    evidence: list[str] = []
    issue_count = 0
    location_token_spans: list[tuple[int, int]] = []

    if location_slug:
        for match in UNRESOLVED_LOCATION_TOKEN_RE.finditer(source):
            issue_count += 1
            location_token_spans.append(match.span())
            _record_match(source, match, "unresolved_location_token", issue_types, evidence)

    for match in GLOBAL_VARIABLE_PLACEHOLDER_RE.finditer(source):
        issue_count += 1
        _record_match(source, match, "global_variable_placeholder", issue_types, evidence)

    for match in CONTEXTUAL_XX_PLACEHOLDER_RE.finditer(source):
        issue_count += 1
        _record_match(source, match, "contextual_xx_placeholder", issue_types, evidence)

    for match in UNRESOLVED_GENERIC_VARIABLE_RE.finditer(source):
        # A location token is already stronger, more specific evidence on an
        # explicit location page. Do not count the same span twice as generic.
        if location_slug and _overlaps(match.span(), location_token_spans):
            continue
        issue_count += 1
        _record_match(source, match, "delimited_template_variable", issue_types, evidence)

    # Wrong-state inference stays deliberately narrower than placeholder detection.
    # A city/market slug proves this is a location template, but it does not prove
    # which U.S. state is intended. Only a state/DC slug can support this claim.
    # Page identity (title/H1) may use the direct state+lender phrase; body copy
    # must explicitly identify this lender/page as the other state. This keeps
    # partner, nationwide, and service-area references out of the finding.
    intended_state = STATE_BY_SLUG.get(location_slug, "") if location_slug else ""
    if intended_state:
        intended_key = intended_state.casefold()
        wrong_state_keys: set[str] = set()
        identity_source = _clean_text(" ".join([str(title or ""), str(h1 or "")]))
        wrong_location_sources = (
            (identity_source, STATE_LENDER_PHRASE_RE),
            (source, STRONG_WRONG_LOCATION_COPY_RE),
        )
        for match_source, pattern in wrong_location_sources:
            for match in pattern.finditer(match_source):
                observed_state = _clean_text(match.group("state"))
                observed_key = observed_state.casefold()
                if observed_key == intended_key or observed_key in wrong_state_keys:
                    continue
                wrong_state_keys.add(observed_key)
                issue_count += 1
                _record_match(match_source, match, "wrong_location_copy", issue_types, evidence)

    return {
        "template_content_issue_types": issue_types,
        "template_content_issue_count": issue_count,
        "template_content_issue_evidence": evidence[:TEMPLATE_CONTENT_EVIDENCE_LIMIT],
    }


def _page_url(page: dict[str, Any]) -> str:
    return str(page.get("final_url") or page.get("url") or page.get("path") or "").strip()


def _dedupe(values: list[str], limit: int) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = _clean_text(raw)
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
        if len(output) >= limit:
            break
    return output


def _location_template_fix(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    affected: list[str] = []
    evidence: list[str] = []
    issue_types: list[str] = []

    for page in pages or []:
        page_issue_types = [
            str(value)
            for value in (page.get("template_content_issue_types") or [])
            if str(value).strip()
        ]
        if not LOCATION_TEMPLATE_ISSUE_TYPES.intersection(page_issue_types):
            continue
        url = _page_url(page)
        if not url or not _location_slug_from_path(url):
            continue
        if not page_has_usable_html(page):
            continue

        affected.append(url)
        for issue_type in page_issue_types:
            if issue_type not in issue_types:
                issue_types.append(issue_type)
        evidence.extend(
            str(value)
            for value in (page.get("template_content_issue_evidence") or [])
            if str(value).strip()
        )

    affected = _dedupe(affected, 150)
    evidence = _dedupe(evidence, TEMPLATE_CONTENT_EVIDENCE_LIMIT)
    if not affected:
        return []

    issue_labels = []
    if "unresolved_location_token" in issue_types:
        issue_labels.append("unresolved location variables")
    if "wrong_location_copy" in issue_types:
        issue_labels.append("wrong-market geographic copy")
    issue_summary = " and ".join(issue_labels) or "broken geographic template content"
    evidence_summary = "; ".join(evidence)

    return [{
        "rule": "broken_location_template_content",
        "category": "web_dev",
        "priority": "high",
        "issue_title": "Fix broken location-page template content",
        "title": "Fix broken location-page template content",
        "plain_english_explanation": (
            f"FixList found {issue_summary} on {len(affected)} location page"
            f"{'s' if len(affected) != 1 else ''}. This points to a shared location template or variable-mapping problem, not separate copy edits."
        ),
        "why_it_matters": (
            "Publishing unresolved placeholders or copy for the wrong market can confuse customers and search engines about which location the page serves, weakening trust and local relevance."
        ),
        "current_value": evidence_summary or f"{len(affected)} location pages contain broken geographic template content.",
        "recommended_value": (
            "Fix the shared location template and its geographic variables so each page renders the intended market name, then verify representative location pages before publishing."
        ),
        "recommendation": (
            "Fix the shared location template and its geographic variables so each page renders the intended market name, then verify representative location pages before publishing."
        ),
        "affected_pages": affected,
        "source_pages": affected[:30],
        "page_template_family": "location_landing",
        "difficulty": "developer",
        "requires_developer": True,
        "requires_approval": False,
        "can_auto_fix": False,
        "who_can_do_this": "your_web_person",
        "source": "page_pattern:broken_location_template_content:location_landing",
        "template_content_issue_types": issue_types,
        "template_content_issue_evidence": evidence,
        "confidence_score": 96,
        "what_to_do_steps": [
            "Open the shared location-page template or CMS component that supplies state and market variables.",
            "Replace unresolved placeholder output and correct any geographic variable mapping that is inserting another market's copy.",
            "Verify several representative location pages, including every example shown by FixList, before publishing.",
            "Publish the shared-template fix and run FixList again to confirm the broken location content is gone.",
        ],
    }]


def _family_label(family: str) -> str:
    labels = {
        "homepage": "homepage",
        "loan_program": "loan pages",
        "activity_detail": "activity pages",
        "booking_or_checkout": "booking and checkout pages",
        "calculator": "calculator pages",
        "collection_page": "collection pages",
        "comparison_page": "comparison pages",
        "contact": "contact pages",
        "conversion": "sign-up and contact pages",
        "product_page": "product pages",
    }
    return labels.get(family, family.replace("_", " ") or "pages")


def _generic_placeholder_fixes(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for page in pages or []:
        if not page_has_usable_html(page):
            continue
        url = _page_url(page)
        if not url or _location_slug_from_path(url):
            # Existing location-template ownership remains exclusive so one
            # visible placeholder cannot create two customer repairs.
            continue
        family = _clean_text(page.get("page_template_family")).lower()
        if family not in GENERIC_PLACEHOLDER_REPAIR_FAMILIES:
            continue
        page_types = [
            str(value)
            for value in (page.get("template_content_issue_types") or [])
            if str(value).strip() in GENERIC_PLACEHOLDER_ISSUE_TYPES
        ]
        if not page_types:
            continue

        group = groups.setdefault(family, {"affected": [], "evidence": [], "types": []})
        group["affected"].append(url)
        group["evidence"].extend(
            str(value)
            for value in (page.get("template_content_issue_evidence") or [])
            if str(value).strip()
        )
        for issue_type in page_types:
            if issue_type not in group["types"]:
                group["types"].append(issue_type)

    fixes: list[dict[str, Any]] = []
    for family, group in groups.items():
        affected = _dedupe(group["affected"], 150)
        evidence = _dedupe(group["evidence"], TEMPLATE_CONTENT_EVIDENCE_LIMIT)
        if not affected:
            continue
        label = _family_label(family)
        evidence_summary = "; ".join(evidence)
        count = len(affected)
        fixes.append({
            "rule": "unresolved_template_placeholder",
            "category": "web_dev",
            "priority": "high",
            "issue_title": f"Replace unfinished placeholder text on {label}",
            "title": f"Replace unfinished placeholder text on {label}",
            "plain_english_explanation": (
                f"FixList found visibly rendered placeholder text on {count} {label if count != 1 else label.rstrip('s')}. "
                "The page output contains unfinished variable markers rather than final customer-facing copy."
            ),
            "why_it_matters": (
                "Visitors can see this unfinished text, which makes the page look broken and can blur the page's meaning for search engines."
            ),
            "current_value": evidence_summary or f"{count} pages contain visibly rendered unresolved placeholder text.",
            "recommended_value": (
                "Replace each unresolved placeholder with the final customer-facing value. If these pages are generated by a shared template or CMS field, correct it there, then verify representative pages before publishing."
            ),
            "recommendation": (
                "Replace each unresolved placeholder with the final customer-facing value. If these pages are generated by a shared template or CMS field, correct it there, then verify representative pages before publishing."
            ),
            "affected_pages": affected,
            "source_pages": affected[:30],
            "page_template_family": family,
            "difficulty": "developer",
            "requires_developer": True,
            "requires_approval": False,
            "can_auto_fix": False,
            "who_can_do_this": "your_web_person",
            "source": f"page_pattern:unresolved_template_placeholder:{family}",
            "template_content_issue_types": list(group["types"]),
            "template_placeholder_evidence": evidence,
            "shared_repair_confirmed": False,
            "evidence_status": "confirmed",
            "verification_state": "verified",
            "confidence_score": 96,
            "what_to_do_steps": [
                "Open each example page and confirm the placeholder is visible in the customer-facing content.",
                "Find the CMS field, component, or template output responsible for that placeholder.",
                "Replace the unfinished marker with the intended customer-facing value without assuming other page families share the same implementation.",
                "Verify the affected examples after publishing and run FixList again.",
            ],
        })
    return fixes


def build_location_template_raw_fixes(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build bounded developer repairs for visible broken-template evidence.

    The historical function name is retained because review.py already consumes
    this hook. Location defects keep their existing single root-cause card;
    generic placeholders are grouped only within one observed template family.
    """
    return _location_template_fix(pages) + _generic_placeholder_fixes(pages)
