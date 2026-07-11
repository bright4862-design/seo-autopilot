from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Anchor not found in {path}: {old[:160]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


review_py = ROOT / "scanner-api/app/review.py"
replace_once(
    review_py,
    "    canonical_fixes = prepare_fixes(raw_fixes + evidence_fixes + page_pattern_fixes + strategic_fixes, site_fingerprint, body, playbook)\n",
    "    canonical_fixes = prepare_fixes(raw_fixes + evidence_fixes + page_pattern_fixes + strategic_fixes, site_fingerprint, body, playbook, pages)\n",
)

sitewide_helpers = r'''

SITEWIDE_COLLAPSE_RULES = {"canonical_missing"}
SITEWIDE_MIN_FAMILIES = 3
SITEWIDE_MIN_PAGES = 10
SITEWIDE_MIN_AFFECTED_RATIO = 0.80
SITEWIDE_MIN_DISCOVERY_COVERAGE = 0.50


def sitewide_collapse_evidence_is_sufficient(site_fingerprint: dict[str, Any]) -> bool:
    """Require a healthy, materially complete crawl before making a site-wide claim."""
    if evidence_is_incomplete(site_fingerprint) or crawl_is_blocked(site_fingerprint):
        return False
    received = int_or_zero(site_fingerprint.get("pages_received"))
    crawled = int_or_zero(site_fingerprint.get("pages_crawled"))
    found = int_or_zero(site_fingerprint.get("pages_found"))
    if received < SITEWIDE_MIN_PAGES:
        return False
    if crawled > 0 and (received / crawled) < 0.80:
        return False
    if found > 0 and crawled > 0 and (crawled / found) < SITEWIDE_MIN_DISCOVERY_COVERAGE:
        return False
    return True


def collapse_sitewide_template_findings(
    fixes: list[dict[str, Any]],
    pages: list[dict[str, Any]],
    site_fingerprint: dict[str, Any],
) -> list[dict[str, Any]]:
    """Collapse one global implementation fault without erasing per-family evidence."""
    if not sitewide_collapse_evidence_is_sufficient(site_fingerprint):
        return fixes

    usable_pages = {
        clean_path(page_evidence_url(page))
        for page in pages
        if clean_path(page_evidence_url(page))
        and not is_blocked_access_page(page)
        and int_or_zero(page.get("status_code") or page.get("status")) < 400
        and page_is_indexable(page)
    }
    if len(usable_pages) < SITEWIDE_MIN_PAGES:
        return fixes

    output = list(fixes)
    for rule in SITEWIDE_COLLAPSE_RULES:
        candidates = [
            fix
            for fix in output
            if str(fix.get("rule") or "") == rule
            and str(fix.get("source") or "").startswith("page_pattern:")
            and str(fix.get("page_scope") or "") not in {"sitewide", "cross_cutting"}
        ]
        families = {
            str(fix.get("page_template_family") or "")
            for fix in candidates
            if str(fix.get("page_template_family") or "") not in {"", "mixed", "sitewide"}
        }
        affected = dedupe_strings([
            clean_path(url)
            for fix in candidates
            for url in (fix.get("affected_pages") or [])
            if clean_path(url)
        ])
        affected_usable = [url for url in affected if url in usable_pages]
        coverage_ratio = len(affected_usable) / max(1, len(usable_pages))
        if (
            len(families) < SITEWIDE_MIN_FAMILIES
            or len(affected_usable) < SITEWIDE_MIN_PAGES
            or coverage_ratio < SITEWIDE_MIN_AFFECTED_RATIO
        ):
            continue

        family_breakdown: dict[str, int] = {}
        representative_pages_by_family: dict[str, list[str]] = {}
        for fix in candidates:
            family = str(fix.get("page_template_family") or "standard")
            family_pages = dedupe_strings([
                clean_path(url)
                for url in (fix.get("affected_pages") or [])
                if clean_path(url) and clean_path(url) in usable_pages
            ])
            if not family_pages:
                continue
            family_breakdown[family] = family_breakdown.get(family, 0) + len(family_pages)
            representative_pages_by_family[family] = dedupe_strings(
                representative_pages_by_family.get(family, []) + family_pages
            )[:3]

        representative_pages = dedupe_strings([
            pages_for_family[0]
            for _, pages_for_family in sorted(representative_pages_by_family.items())
            if pages_for_family
        ])
        base = max(candidates, key=fix_sort_key)
        collapse_id = stable_id(
            f"sitewide|{rule}|{','.join(sorted(families))}|{len(affected_usable)}|{len(usable_pages)}"
        )
        title = "Add canonical URLs across the site"
        explanation = (
            "Canonical URLs are missing across nearly every indexable page in the scanned evidence. "
            "This points to one global document-head or CMS template implementation issue, not separate page-family problems."
        )
        why = (
            "Without consistent canonical URLs, search engines have a weaker signal for which public URL should represent each page. "
            "Because the same gap spans multiple page families, one global implementation fix should resolve it."
        )
        recommendation = (
            "Ask your web person to add a self-referencing canonical URL in the global document head or shared layout, "
            "then verify representative pages from every affected family."
        )
        steps = [
            "Open the global document head, root layout, or shared CMS template that renders canonical tags.",
            "Add one self-referencing canonical URL based on each page's final public URL.",
            "Verify at least one representative conversion, loan, location, article, legal, contact, standard, and homepage page.",
            "Publish the global change and run FixList again to confirm the site-wide canonical gap is resolved.",
        ]
        collapsed = {
            **base,
            "id": collapse_id,
            "fix_id": collapse_id,
            "issue_title": title,
            "title": title,
            "plain_english_explanation": explanation,
            "plain_english_summary": explanation,
            "why_it_matters": why,
            "recommendation": recommendation,
            "recommended_value": recommendation,
            "ai_recommendation": recommendation,
            "simple_next_step": recommendation,
            "current_value": (
                f"{len(affected_usable)} of {len(usable_pages)} indexable pages in the crawl are missing canonical URLs "
                f"across {len(family_breakdown)} page families."
            ),
            "page_url": representative_pages[0] if representative_pages else affected_usable[0],
            "affected_pages": affected_usable[:150],
            "source_pages": representative_pages[:30],
            "page_count": len(affected_usable),
            "page_scope": "sitewide",
            "page_template_family": "",
            "family_breakdown": dict(sorted(family_breakdown.items())),
            "representative_pages_by_family": dict(sorted(representative_pages_by_family.items())),
            "sitewide_evidence": {
                "affected_indexable_pages": len(affected_usable),
                "indexable_pages_reviewed": len(usable_pages),
                "coverage_ratio": round(coverage_ratio, 3),
                "family_count": len(family_breakdown),
            },
            "source": f"review_sitewide_collapse:{rule}",
            "priority": "critical",
            "difficulty": "developer",
            "status": "needs_developer",
            "requires_developer": True,
            "requires_approval": False,
            "can_auto_fix": False,
            "who_can_do_this": "your_web_person",
            "what_to_do": steps,
            "what_to_do_steps": steps,
            "fix_steps": steps,
            "page_type": "site_level",
            "business_importance": "site_level",
            "is_low_value_page": False,
            "is_important_business_page": False,
            "page_value_score": 100,
            "page_value_label": "Site-wide setup",
            "primary_defect_class": "structural",
            "reach_score": 100,
            "overall_priority_score": max(96, max(int_or_zero(fix.get("overall_priority_score")) for fix in candidates)),
            "evidence_confidence": max(int_or_zero(fix.get("evidence_confidence")) for fix in candidates),
        }
        candidate_ids = {id(fix) for fix in candidates}
        output = [fix for fix in output if id(fix) not in candidate_ids]
        output.append(collapsed)
    return output
'''
replace_once(
    review_py,
    "\n\ndef prepare_fixes(raw_fixes: list[dict[str, Any]], site_fingerprint: dict[str, Any], body: dict[str, Any], playbook: dict[str, Any]) -> list[dict[str, Any]]:\n",
    sitewide_helpers + "\n\ndef prepare_fixes(raw_fixes: list[dict[str, Any]], site_fingerprint: dict[str, Any], body: dict[str, Any], playbook: dict[str, Any], pages: list[dict[str, Any]]) -> list[dict[str, Any]]:\n",
)
replace_once(
    review_py,
    "    scored = suppress_duplicate_group_cards(scored)\n    return sorted(scored, key=fix_sort_key, reverse=True)[:36]\n",
    "    scored = suppress_duplicate_group_cards(scored)\n    scored = collapse_sitewide_template_findings(scored, pages, site_fingerprint)\n    return sorted(scored, key=fix_sort_key, reverse=True)[:36]\n",
)
replace_once(
    review_py,
    '        "page_template_family": "mixed" if is_cross_cutting_evidence(fix) else fix.get("page_template_family") or get_template_family(page_url),\n',
    '        "page_scope": "cross_cutting" if is_cross_cutting_evidence(fix) else fix.get("page_scope") or ("family" if len(affected_pages) > 1 else "page"),\n        "page_template_family": "mixed" if is_cross_cutting_evidence(fix) else fix.get("page_template_family") or get_template_family(page_url),\n',
)
replace_once(
    review_py,
    '''def group_page_recommendations(fixes: list[dict[str, Any]]) -> list[dict[str, Any]]:\n    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)\n    for fix in fixes:\n        groups[str(fix.get("page_template_family") or "site")].append(fix)\n    return [{"template_family": family, "count": len(items), "top_recommendations": items[:5]} for family, items in list(groups.items())[:12]]\n''',
    '''def group_page_recommendations(fixes: list[dict[str, Any]]) -> list[dict[str, Any]]:\n    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)\n    for fix in fixes:\n        scope = str(fix.get("page_scope") or "")\n        key = scope if scope in {"sitewide", "cross_cutting"} else str(fix.get("page_template_family") or "site")\n        groups[key].append(fix)\n    return [{"template_family": family, "count": len(items), "top_recommendations": items[:5]} for family, items in list(groups.items())[:12]]\n''',
)

presentation_test = ROOT / "scanner-api/tests/test_review_presentation_contract.py"
text = presentation_test.read_text(encoding="utf-8")
text = text.replace(
    '    assert card["page_template_family"] == "mixed"\n',
    '    assert card["page_template_family"] == "mixed"\n    assert card["page_scope"] == "cross_cutting"\n',
    1,
)
addition = r'''


def _run_with_coverage(pages, *, pages_found, pages_crawled=None):
    crawled = len(pages) if pages_crawled is None else pages_crawled
    return run_review({
        "website_url": "https://example.com",
        "pages": pages,
        "scan_coverage": {
            "pages_found": pages_found,
            "pages_crawled": crawled,
            "sampled_pages_sent_to_ai": len(pages),
        },
    })


def _sitewide_fixture(*, canonical="", image_missing_alt_count=0):
    families = {
        "homepage": 1,
        "conversion": 4,
        "loan_program": 5,
        "location_landing": 8,
        "guide_article": 6,
        "legal_info": 2,
        "contact": 1,
        "standard": 3,
    }
    pages = []
    for family, count in families.items():
        for index in range(count):
            path = "/" if family == "homepage" else f"/{family}/{index}"
            pages.append(_page(
                path,
                family,
                canonical=canonical or "",
                image_missing_alt_count=image_missing_alt_count,
            ))
    return families, pages


def test_sitewide_canonical_collapse_preserves_family_evidence():
    families, pages = _sitewide_fixture(canonical="")
    result = _run_with_coverage(pages, pages_found=36)
    canonical_cards = [fix for fix in result["cleaned_fixes"] if fix.get("rule") == "canonical_missing"]

    assert len(canonical_cards) == 1
    card = canonical_cards[0]
    assert card["title"] == "Add canonical URLs across the site"
    assert card["page_scope"] == "sitewide"
    assert card["page_template_family"] == ""
    assert card["page_count"] == len(pages)
    assert card["family_breakdown"] == families
    assert set(card["representative_pages_by_family"]) == set(families)
    assert len(card["source_pages"]) == len(families)
    assert card["sitewide_evidence"]["coverage_ratio"] == 1.0
    assert "global document head" in card["plain_english_explanation"].lower()


def test_sitewide_collapse_does_not_overclaim_on_shallow_discovery_coverage():
    _, pages = _sitewide_fixture(canonical="")
    result = _run_with_coverage(pages, pages_found=200, pages_crawled=len(pages))
    canonical_cards = [fix for fix in result["cleaned_fixes"] if fix.get("rule") == "canonical_missing"]

    assert len(canonical_cards) >= 3
    assert not any(fix.get("page_scope") == "sitewide" for fix in canonical_cards)


def test_content_specific_image_findings_do_not_collapse_sitewide():
    _, pages = _sitewide_fixture(
        canonical="https://example.com/canonical",
        image_missing_alt_count=2,
    )
    result = _run_with_coverage(pages, pages_found=36)
    image_cards = [fix for fix in result["cleaned_fixes"] if fix.get("rule") == "image_alt_text"]

    assert len(image_cards) >= 3
    assert not any(fix.get("page_scope") == "sitewide" for fix in image_cards)
'''
if "test_sitewide_canonical_collapse_preserves_family_evidence" not in text:
    text = text.rstrip() + addition + "\n"
presentation_test.write_text(text, encoding="utf-8")

review_contract = ROOT / "src/lib/reviewContract.js"
text = review_contract.read_text(encoding="utf-8")
if "export function normalizeReviewScope" not in text:
    text += r'''

export function normalizeReviewScope(fix = {}, fallbackFamily = "") {
  const explicitScope = String(fix?.page_scope || "").toLowerCase();
  const affected = Array.isArray(fix?.affected_pages) ? fix.affected_pages : [];
  const pageScope = ["sitewide", "cross_cutting", "family", "page"].includes(explicitScope)
    ? explicitScope
    : fix?.page_template_family === "mixed"
      ? "cross_cutting"
      : affected.length > 1
        ? "family"
        : "page";
  return {
    page_scope: pageScope,
    page_template_family: pageScope === "sitewide"
      ? ""
      : String(fix?.page_template_family || fallbackFamily || ""),
  };
}
'''
    review_contract.write_text(text, encoding="utf-8")

scan_form = ROOT / "src/components/scan/ScanWebsiteForm.jsx"
replace_once(
    scan_form,
    'import { normalizeActionPriority, selectFinalReviewFixes } from "@/lib/reviewContract";',
    'import { normalizeActionPriority, normalizeReviewScope, selectFinalReviewFixes } from "@/lib/reviewContract";',
)
replace_once(
    scan_form,
    '  const title = cleanString(fix.title || fix.issue_title) || defaultTitle(category);\n',
    '  const title = cleanString(fix.title || fix.issue_title) || defaultTitle(category);\n  const reviewScope = normalizeReviewScope(fix, classifyTemplateFamily(fallbackPage));\n',
)
replace_once(
    scan_form,
    'page_template_family: fix.page_template_family || classifyTemplateFamily(fallbackPage), primary_defect_class:',
    'page_scope: reviewScope.page_scope, page_template_family: reviewScope.page_template_family, family_breakdown: fix.family_breakdown && typeof fix.family_breakdown === "object" ? fix.family_breakdown : {}, representative_pages_by_family: fix.representative_pages_by_family && typeof fix.representative_pages_by_family === "object" ? fix.representative_pages_by_family : {}, sitewide_evidence: fix.sitewide_evidence && typeof fix.sitewide_evidence === "object" ? fix.sitewide_evidence : {}, primary_defect_class:',
)

frontend_test = ROOT / "tests/frontend/review_contract.test.mjs"
text = frontend_test.read_text(encoding="utf-8")
text = text.replace(
    'import { normalizeActionPriority } from "../../src/lib/reviewContract.js";',
    'import { normalizeActionPriority, normalizeReviewScope } from "../../src/lib/reviewContract.js";',
    1,
)
frontend_addition = r'''

test("sitewide scope does not masquerade as a template family", () => {
  assert.deepEqual(
    normalizeReviewScope({ page_scope: "sitewide", page_template_family: "loan_program", affected_pages: ["/a", "/b"] }, "standard"),
    { page_scope: "sitewide", page_template_family: "" },
  );
});

test("cross-cutting evidence keeps the mixed compatibility marker", () => {
  assert.deepEqual(
    normalizeReviewScope({ page_template_family: "mixed", affected_pages: ["/a", "/b"] }, "standard"),
    { page_scope: "cross_cutting", page_template_family: "mixed" },
  );
});

test("normal reviewed findings retain their family", () => {
  assert.deepEqual(
    normalizeReviewScope({ page_scope: "family", page_template_family: "loan_program", affected_pages: ["/a", "/b"] }, "standard"),
    { page_scope: "family", page_template_family: "loan_program" },
  );
});
'''
if "sitewide scope does not masquerade as a template family" not in text:
    text = text.rstrip() + frontend_addition + "\n"
frontend_test.write_text(text, encoding="utf-8")
