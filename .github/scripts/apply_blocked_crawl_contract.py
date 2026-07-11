from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Anchor not found in {path}: {old[:180]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_between(path: Path, start: str, end: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    start_index = text.find(start)
    if start_index < 0:
        raise SystemExit(f"Start anchor not found in {path}: {start!r}")
    end_index = text.find(end, start_index)
    if end_index < 0:
        raise SystemExit(f"End anchor not found in {path}: {end!r}")
    path.write_text(text[:start_index] + replacement + text[end_index:], encoding="utf-8")


review = ROOT / "scanner-api/app/review.py"
replace_once(
    review,
    "                extra=evidence_extra(group),\n",
    "                extra={\n"
    "                    **evidence_extra(group),\n"
    "                    \"evidence_status\": \"needs_verification\",\n"
    "                    \"verification_state\": \"needs_verification\",\n"
    "                    \"limitation_code\": \"rate_limit_requires_log_confirmation\",\n"
    "                },\n",
)

new_review_payload = '''def build_review_payload(body: dict[str, Any], pages: list[dict[str, Any]], fixes: list[dict[str, Any]], site_fingerprint: dict[str, Any], playbook: dict[str, Any], website_url: str) -> dict[str, Any]:
    incomplete = evidence_is_incomplete(site_fingerprint)
    blocked = crawl_is_blocked(site_fingerprint)
    rate_limited = has_rate_limit_evidence(fixes)
    quality = review_input_quality(body, site_fingerprint)
    health_score = compute_health_score(fixes, site_fingerprint)
    blocked_count = int_or_zero(site_fingerprint.get("blocked_or_429_pages"))
    reviewed_count = max(
        int_or_zero(site_fingerprint.get("pages_received")),
        int_or_zero(site_fingerprint.get("pages_crawled")),
    )

    summary = f"FixList recognized this as {playbook['label']} and used the {playbook['label']} playbook. The scanner reviewed {site_fingerprint['pages_crawled']} pages"
    if site_fingerprint.get("pages_found"):
        summary += f" out of about {site_fingerprint['pages_found']} discovered URLs"
    summary += f". Start with the highest-impact items on {', '.join(playbook['priority_pages'][:3])}."
    if blocked:
        summary = (
            f"FixList could not complete a reliable page-quality review because {blocked_count} of {reviewed_count or blocked_count} reviewed pages "
            "returned HTTP 429, bot-protection, or connection-verification responses. The score is provisional until server, CDN, "
            "firewall, or bot-protection logs confirm legitimate crawler access."
        )
    elif incomplete:
        summary = INCOMPLETE_REVIEW_WARNING
    elif rate_limited:
        summary += (
            f" {blocked_count or 1} reviewed page{'s' if (blocked_count or 1) != 1 else ''} returned HTTP 429 or an access-verification response. "
            "The score is provisional until those results are checked in access logs."
        )

    working = [f"FixList detected a {playbook['label']} pattern."] if site_fingerprint["primary_archetype"] != "general" else []
    top_concerns = [fix.get("issue_title") or fix.get("title") for fix in fixes[:3] if fix.get("issue_title") or fix.get("title")]
    quick_wins = [fix.get("issue_title") or fix.get("title") for fix in fixes if fix.get("difficulty") != "developer"][:3]
    bigger_projects = [fix.get("issue_title") or fix.get("title") for fix in fixes if fix.get("difficulty") == "developer" or fix.get("requires_developer")][:3]
    limitations = [
        "This scan is read-only and cannot confirm private analytics, paid search data, conversions, or server logs."
    ]
    if rate_limited:
        limitations.append(
            "HTTP 429 and connection-verification results need access-log confirmation before being treated as confirmed broken customer pages."
        )

    access_evidence_state = "blocked" if blocked else "partial_access_limited" if rate_limited else "complete"
    review_confidence_state = (
        "blocked_access_needs_verification"
        if blocked
        else "incomplete_evidence"
        if incomplete
        else "partial_access_needs_verification"
        if rate_limited
        else "complete"
    )
    scan_status = (
        "blocked_or_incomplete"
        if blocked
        else "incomplete_evidence"
        if incomplete
        else "complete_with_access_limitations"
        if rate_limited
        else "complete"
    )
    score_is_provisional = bool(blocked or incomplete or rate_limited)

    report = {
        "health_score": health_score,
        "score": health_score,
        "overall_explanation": summary,
        "health_grade": "Blocked / incomplete" if blocked else "Scan incomplete" if incomplete else "Strong" if health_score >= 90 else "Good" if health_score >= 80 else "Needs work" if health_score >= 65 else "Major issues",
        "what_is_working": working,
        "top_concerns": top_concerns,
        "quick_wins": quick_wins,
        "bigger_projects": bigger_projects,
        "limitations": limitations,
        "next_best_step": "Ask your web person to verify crawler access, rate limits, CDN, firewall, and bot-protection settings." if blocked else "Re-run the scan — page evidence did not reach AI Review." if incomplete else ((fixes[0].get("issue_title") or fixes[0].get("title")) if fixes else "Review the first FixList item."),
        "scan_status": scan_status,
        "review_confidence_state": review_confidence_state,
        "score_is_provisional": score_is_provisional,
        "access_evidence_state": access_evidence_state,
    }
    pages_returned = pages[:80]
    return {
        "plain_english_summary": summary,
        "website_health_report": report,
        "health_explanation": summary,
        "customer_summary": summary,
        "top_recommended_actions": fixes[:5],
        "recommended_actions": fixes,
        "cleaned_fixes": fixes,
        "raw_fixes": fixes,
        "fixes": fixes,
        "findings": fixes,
        "recommendations": fixes,
        "competitor_insights": [],
        "grouped_page_recommendations": group_page_recommendations(fixes),
        "ignored_low_value_pages": [clean_path(page_evidence_url(page)) for page in pages if is_low_value_page(page_evidence_url(page))][:30],
        "positive_findings": working,
        "ai_rewrites_applied": 0,
        "crawled_pages": pages_returned,
        "pages": pages_returned,
        "health_score": health_score,
        "site_fingerprint": {**site_fingerprint, "review_input_quality": quality},
        "review_input_quality": {**quality, "access_evidence_state": access_evidence_state, "score_is_provisional": score_is_provisional},
        "review_quality_gate_version": QUALITY_GATE_VERSION,
        "evidence_complete": not incomplete,
        "scan_status": scan_status,
        "review_confidence_state": review_confidence_state,
        "score_is_provisional": score_is_provisional,
        "access_evidence_state": access_evidence_state,
        "archetype_playbook": {
            "label": playbook["label"],
            "priority_pages": playbook["priority_pages"],
            "priority_issues": playbook["priority_issues"],
            "demote": playbook["demote"],
            "owner_rule": playbook["owner_rule"],
        },
        "technical_audit_summary": body.get("technical_audit_summary"),
        "screaming_frog_lite_enabled": bool(body.get("screaming_frog_lite_enabled")),
        "audit_profile": clean_str(body.get("scanner_profile") or body.get("audit_profile") or ""),
        "scanner_version": body.get("scanner_version") or body.get("version") or "",
        "advanced_scan_backend": body.get("advanced_scan_backend") or deep_get(body, "technical_audit_summary", "advanced_scan_backend") or "",
        "deno_fallback_used": bool(body.get("deno_fallback_used") or deep_get(body, "technical_audit_summary", "deno_fallback_used")),
        "website_url": website_url,
        "seo_score": health_score,
        "simple_summary": summary,
        "scanned_pages": pages_returned,
        "scan_summary": {
            "health_score": health_score,
            "score": health_score,
            "pages_scanned": site_fingerprint["pages_crawled"],
            "plain_english_summary": summary,
            "site_fingerprint": site_fingerprint,
            "review_input_quality": quality,
            "scan_status": scan_status,
            "review_confidence_state": review_confidence_state,
            "score_is_provisional": score_is_provisional,
            "access_evidence_state": access_evidence_state,
        },
        "scoring_model": SCORING_MODEL,
    }
'''
replace_between(review, "def build_review_payload(", "\n\ndef make_fix(", new_review_payload)

presentation_tests = ROOT / "scanner-api/tests/test_review_presentation_contract.py"
text = presentation_tests.read_text(encoding="utf-8")
marker = "def test_fully_blocked_crawl_is_provisional_and_needs_verification():"
if marker not in text:
    text += r'''


def _rate_limited_page(path, family="standard"):
    return _page(
        path,
        family,
        status_code=429,
        fetch_error="HTTP 429 Too Many Requests",
        title="Connection verification",
        url_confidence="linked_but_failed",
        source_pages=["/"],
    )


def test_fully_blocked_crawl_is_provisional_and_needs_verification():
    pages = [
        _rate_limited_page("/category/one", "collection_page"),
        _rate_limited_page("/category/two", "collection_page"),
        _rate_limited_page("/activity/one", "activity_detail"),
        _rate_limited_page("/activity/two", "activity_detail"),
        _rate_limited_page("/locations/paris", "location_landing"),
        _rate_limited_page("/guide/help", "guide_article"),
    ]
    result = _run_with_coverage(pages, pages_found=len(pages))
    rate_cards = [fix for fix in result["cleaned_fixes"] if fix.get("rule") == "rate_limited_page"]

    assert len(rate_cards) == 1
    card = rate_cards[0]
    assert card["page_scope"] == "cross_cutting"
    assert card["page_template_family"] == "mixed"
    assert card["evidence_status"] == "needs_verification"
    assert card["verification_state"] == "needs_verification"
    assert card["limitation_code"] == "rate_limit_requires_log_confirmation"
    assert card["status_codes"] == [429]
    assert len(card["affected_pages"]) == len(pages)
    assert result["scan_status"] == "blocked_or_incomplete"
    assert result["review_confidence_state"] == "blocked_access_needs_verification"
    assert result["score_is_provisional"] is True
    assert result["access_evidence_state"] == "blocked"
    assert result["website_health_report"]["health_grade"] == "Blocked / incomplete"
    assert result["health_score"] <= 45
    assert result["review_input_quality"]["access_evidence_state"] == "blocked"
    assert result["review_input_quality"]["score_is_provisional"] is True
    assert "score is provisional" in result["customer_summary"].lower()
    assert any("HTTP 429" in item for item in result["website_health_report"]["limitations"])
    assert not any(fix.get("page_scope") == "sitewide" for fix in result["cleaned_fixes"])
    assert not any(fix.get("rule") in {"canonical_missing", "missing_h1", "missing_meta_description", "image_alt_text"} for fix in result["cleaned_fixes"])


def test_partially_blocked_crawl_is_complete_with_access_limitations():
    pages = [
        _rate_limited_page("/category/one", "collection_page"),
        _rate_limited_page("/activity/one", "activity_detail"),
        _page("/", "homepage"),
        _page("/contact", "contact"),
        _page("/guide/one", "guide_article"),
        _page("/locations/paris", "location_landing"),
    ]
    result = _run_with_coverage(pages, pages_found=len(pages))
    card = _fix(result, "rate_limited_page")

    assert card["page_scope"] == "cross_cutting"
    assert card["page_template_family"] == "mixed"
    assert card["evidence_status"] == "needs_verification"
    assert result["scan_status"] == "complete_with_access_limitations"
    assert result["review_confidence_state"] == "partial_access_needs_verification"
    assert result["score_is_provisional"] is True
    assert result["access_evidence_state"] == "partial_access_limited"
    assert result["website_health_report"]["health_grade"] != "Blocked / incomplete"
    assert "score is provisional" in result["customer_summary"].lower()
    assert any("HTTP 429" in item for item in result["website_health_report"]["limitations"])


def test_clean_crawl_is_not_marked_provisional():
    result = _run_with_coverage([_page("/", "homepage"), _page("/contact", "contact")], pages_found=2)

    assert result["score_is_provisional"] is False
    assert result["access_evidence_state"] == "complete"
    assert result["scan_status"] in {"complete", "complete_no_high_confidence_findings"}
    assert not any("HTTP 429" in item for item in result["website_health_report"]["limitations"])
'''
    presentation_tests.write_text(text, encoding="utf-8")


contract = ROOT / "src/lib/reviewContract.js"
text = contract.read_text(encoding="utf-8")
if "export function normalizeFindingEvidence" not in text:
    text += r'''


export function normalizeFindingEvidence(fix = {}) {
  const rule = String(fix?.rule || fix?.issue_type || "").toLowerCase();
  const source = String(fix?.source || "").toLowerCase();
  const rateLimited =
    ["rate_limited_page", "blocked_page", "blocked_page_429", "scanner_blocked"].includes(rule) ||
    source.startsWith("scanner_verified_failed_pages:429");
  const explicitEvidence = String(fix?.evidence_status || "").toLowerCase();
  const evidenceStatus = explicitEvidence || (rateLimited ? "needs_verification" : "confirmed");
  return {
    evidence_status: evidenceStatus,
    verification_state: String(fix?.verification_state || "").toLowerCase() || evidenceStatus,
    limitation_code: String(fix?.limitation_code || "") || (rateLimited ? "rate_limit_requires_log_confirmation" : ""),
  };
}


export function normalizeReviewEvidenceState(source = {}) {
  const report = source?.website_health_report || {};
  const explicitStatus = String(source?.scan_status || report?.scan_status || "");
  const blocked = explicitStatus === "blocked_or_incomplete";
  const partial = explicitStatus === "complete_with_access_limitations";
  const incomplete = explicitStatus === "incomplete_evidence";
  const noFindings = source?.no_high_confidence_findings === true || explicitStatus === "complete_no_high_confidence_findings";
  const scoreIsProvisional = Boolean(source?.score_is_provisional ?? report?.score_is_provisional) || blocked || partial || incomplete;
  const accessEvidenceState = String(source?.access_evidence_state || report?.access_evidence_state || "") ||
    (blocked ? "blocked" : partial ? "partial_access_limited" : "");
  const reviewConfidenceState = String(source?.review_confidence_state || report?.review_confidence_state || "") ||
    (blocked
      ? "blocked_access_needs_verification"
      : partial
        ? "partial_access_needs_verification"
        : incomplete
          ? "incomplete_evidence"
          : noFindings
            ? "no_high_confidence_findings"
            : "");
  return {
    scan_status: explicitStatus,
    review_confidence_state: reviewConfidenceState,
    score_is_provisional: scoreIsProvisional,
    access_evidence_state: accessEvidenceState,
  };
}
'''
    contract.write_text(text, encoding="utf-8")


scan_form = ROOT / "src/components/scan/ScanWebsiteForm.jsx"
replace_once(
    scan_form,
    'import { normalizeActionPriority, normalizeReviewScope, selectFinalReviewFixes } from "@/lib/reviewContract";\n',
    'import { normalizeActionPriority, normalizeFindingEvidence, normalizeReviewEvidenceState, normalizeReviewScope, selectFinalReviewFixes } from "@/lib/reviewContract";\n',
)
replace_once(
    scan_form,
    "  const siteFingerprint = normalizeSiteFingerprint(aiData?.site_fingerprint || aiData?.scan_summary?.site_fingerprint || {}, pages);\n\n  return {\n",
    "  const siteFingerprint = normalizeSiteFingerprint(aiData?.site_fingerprint || aiData?.scan_summary?.site_fingerprint || {}, pages);\n"
    "  const reviewEvidenceState = normalizeReviewEvidenceState(aiData);\n\n"
    "  return {\n",
)
replace_once(
    scan_form,
    '    review_confidence_state: aiData?.review_confidence_state || (noHighConfidenceFindings ? "no_high_confidence_findings" : ""),\n    zero_fix_confidence_version: aiData?.zero_fix_confidence_version || "",\n    scan_status: aiData?.scan_status || (noHighConfidenceFindings ? "complete_no_high_confidence_findings" : "complete"),\n',
    '    review_confidence_state: reviewEvidenceState.review_confidence_state || (noHighConfidenceFindings ? "no_high_confidence_findings" : ""),\n    score_is_provisional: reviewEvidenceState.score_is_provisional,\n    access_evidence_state: reviewEvidenceState.access_evidence_state,\n    zero_fix_confidence_version: aiData?.zero_fix_confidence_version || "",\n    scan_status: reviewEvidenceState.scan_status || (noHighConfidenceFindings ? "complete_no_high_confidence_findings" : "complete"),\n',
)
replace_once(
    scan_form,
    '    review_confidence_state: aiData?.review_confidence_state || (noHighConfidenceFindings ? "no_high_confidence_findings" : ""),\n    zero_fix_confidence_version: aiData?.zero_fix_confidence_version || "",\n    scan_status: aiData?.scan_status || (noHighConfidenceFindings ? "complete_no_high_confidence_findings" : "complete"),\n',
    '    review_confidence_state: reviewEvidenceState.review_confidence_state || (noHighConfidenceFindings ? "no_high_confidence_findings" : ""),\n    score_is_provisional: reviewEvidenceState.score_is_provisional,\n    access_evidence_state: reviewEvidenceState.access_evidence_state,\n    zero_fix_confidence_version: aiData?.zero_fix_confidence_version || "",\n    scan_status: reviewEvidenceState.scan_status || (noHighConfidenceFindings ? "complete_no_high_confidence_findings" : "complete"),\n',
)
replace_once(
    scan_form,
    "  const reviewScope = normalizeReviewScope(fix, classifyTemplateFamily(fallbackPage));\n  return {",
    "  const reviewScope = normalizeReviewScope(fix, classifyTemplateFamily(fallbackPage));\n"
    "  const findingEvidence = normalizeFindingEvidence(fix);\n"
    "  return {",
)
replace_once(
    scan_form,
    'confidence_score: typeof fix.confidence_score === "number" ? fix.confidence_score : 90, source: fix.source || "", business_importance:',
    'confidence_score: typeof fix.confidence_score === "number" ? fix.confidence_score : 90, source: fix.source || "", evidence_status: findingEvidence.evidence_status, verification_state: findingEvidence.verification_state, limitation_code: findingEvidence.limitation_code, status_codes: firstArray([fix.status_codes]).map(Number).filter(Boolean), business_importance:',
)
replace_once(
    scan_form,
    '    scan_status: ai.scan_status || "",\n    next_best_step: ai.next_best_step || ai.website_health_report?.next_best_step || "",\n',
    '    scan_status: ai.scan_status || "",\n    review_confidence_state: ai.review_confidence_state || ai.website_health_report?.review_confidence_state || "",\n    score_is_provisional: Boolean(ai.score_is_provisional ?? ai.website_health_report?.score_is_provisional),\n    access_evidence_state: ai.access_evidence_state || ai.website_health_report?.access_evidence_state || "",\n    next_best_step: ai.next_best_step || ai.website_health_report?.next_best_step || "",\n',
)
replace_once(
    scan_form,
    'function slimHealthReport(report = {}, summaryText = "", healthScore = 0) {\n  return { health_score:',
    'function slimHealthReport(report = {}, summaryText = "", healthScore = 0) {\n  return { scan_status: report.scan_status || "", review_confidence_state: report.review_confidence_state || "", score_is_provisional: Boolean(report.score_is_provisional), access_evidence_state: report.access_evidence_state || "", health_score:',
)

frontend_tests = ROOT / "tests/frontend/review_contract.test.mjs"
text = frontend_tests.read_text(encoding="utf-8")
text = text.replace(
    'import { normalizeActionPriority, normalizeReviewScope } from "../../src/lib/reviewContract.js";\n',
    'import { normalizeActionPriority, normalizeFindingEvidence, normalizeReviewEvidenceState, normalizeReviewScope } from "../../src/lib/reviewContract.js";\n',
    1,
)
if 'test("rate-limit findings retain a needs-verification contract"' not in text:
    text += r'''


test("rate-limit findings retain a needs-verification contract", () => {
  assert.deepEqual(
    normalizeFindingEvidence({ rule: "rate_limited_page", source: "scanner_verified_failed_pages:429" }),
    {
      evidence_status: "needs_verification",
      verification_state: "needs_verification",
      limitation_code: "rate_limit_requires_log_confirmation",
    },
  );
});


test("explicit finding evidence is preserved", () => {
  assert.deepEqual(
    normalizeFindingEvidence({ rule: "canonical_missing", evidence_status: "sample_based", verification_state: "sample_based", limitation_code: "sample_only" }),
    {
      evidence_status: "sample_based",
      verification_state: "sample_based",
      limitation_code: "sample_only",
    },
  );
});


test("blocked review state survives frontend record normalization", () => {
  const state = normalizeReviewEvidenceState({
    scan_status: "blocked_or_incomplete",
    review_confidence_state: "blocked_access_needs_verification",
    score_is_provisional: true,
    access_evidence_state: "blocked",
    website_health_report: { health_grade: "Blocked / incomplete" },
  });
  assert.deepEqual(state, {
    scan_status: "blocked_or_incomplete",
    review_confidence_state: "blocked_access_needs_verification",
    score_is_provisional: true,
    access_evidence_state: "blocked",
  });
});


test("partial access limitations remain provisional in the saved contract", () => {
  assert.deepEqual(
    normalizeReviewEvidenceState({ scan_status: "complete_with_access_limitations" }),
    {
      scan_status: "complete_with_access_limitations",
      review_confidence_state: "partial_access_needs_verification",
      score_is_provisional: true,
      access_evidence_state: "partial_access_limited",
    },
  );
});
'''
    frontend_tests.write_text(text, encoding="utf-8")
