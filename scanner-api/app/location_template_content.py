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


def detect_location_template_content(
    path: str,
    title: str,
    h1: str,
    visible_text: str,
) -> dict[str, Any]:
    """Return bounded broken-template evidence for explicit location landing pages."""
    location_slug = _location_slug_from_path(path)
    if not location_slug:
        return {
            "template_content_issue_types": [],
            "template_content_issue_count": 0,
            "template_content_issue_evidence": [],
        }

    # extract.py's visible_text already contains the document title and headings.
    # Scan that source once so placeholder counts and evidence are not duplicated.
    source = _clean_text(visible_text)
    issue_types: list[str] = []
    evidence: list[str] = []
    issue_count = 0

    for match in UNRESOLVED_LOCATION_TOKEN_RE.finditer(source):
        issue_count += 1
        if "unresolved_location_token" not in issue_types:
            issue_types.append("unresolved_location_token")
        snippet = _evidence_snippet(source, match.start(), match.end())
        if snippet and snippet not in evidence and len(evidence) < TEMPLATE_CONTENT_EVIDENCE_LIMIT:
            evidence.append(snippet)

    # Wrong-state inference stays deliberately narrower than placeholder detection.
    # A city/market slug proves this is a location template, but it does not prove
    # which U.S. state is intended. Only a state/DC slug can support this claim.
    # Page identity (title/H1) may use the direct state+lender phrase; body copy
    # must explicitly identify this lender/page as the other state. This keeps
    # partner, nationwide, and service-area references out of the finding.
    intended_state = STATE_BY_SLUG.get(location_slug, "")
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
                if "wrong_location_copy" not in issue_types:
                    issue_types.append("wrong_location_copy")
                snippet = _evidence_snippet(match_source, match.start(), match.end())
                if (
                    snippet
                    and snippet not in evidence
                    and len(evidence) < TEMPLATE_CONTENT_EVIDENCE_LIMIT
                ):
                    evidence.append(snippet)

    return {
        "template_content_issue_types": issue_types,
        "template_content_issue_count": issue_count,
        "template_content_issue_evidence": evidence[:TEMPLATE_CONTENT_EVIDENCE_LIMIT],
    }


def _page_url(page: dict[str, Any]) -> str:
    return str(page.get("url") or page.get("final_url") or page.get("path") or "").strip()


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


def build_location_template_raw_fixes(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group broken location copy into one developer-owned root-cause repair."""
    affected: list[str] = []
    evidence: list[str] = []
    issue_types: list[str] = []

    for page in pages or []:
        page_issue_types = [
            str(value)
            for value in (page.get("template_content_issue_types") or [])
            if str(value).strip()
        ]
        if not page_issue_types:
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
