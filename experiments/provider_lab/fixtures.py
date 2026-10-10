from __future__ import annotations

from .contracts import (
    AuthorityManifest,
    EvaluationCase,
    REPAIR_CONTRACT_V2,
    REPAIR_PRIORITY_MODEL_V2,
)

RELEASE_FINGERPRINT = "51c813a6219b4e70"


def _authority(scan_id: str) -> AuthorityManifest:
    return AuthorityManifest(
        scan_id=scan_id,
        release_fingerprint=RELEASE_FINGERPRINT,
        repair_contract_version=REPAIR_CONTRACT_V2,
        repair_snapshot_contract_version=REPAIR_CONTRACT_V2,
        repair_snapshot_contract_complete=True,
        repair_priority_model_version=REPAIR_PRIORITY_MODEL_V2,
    )


def representative_cases() -> tuple[EvaluationCase, ...]:
    """Sanitized provider-facing fixtures spanning high-value FixList questions."""

    return (
        EvaluationCase(
            case_id="redirects-internal-links",
            question="What should I fix first and can I do it myself?",
            authority=_authority("fixture-redirects"),
            evidence={
                "release_gate_eligible": True,
                "scan_id": "fixture-redirects",
                "project_id": "fixture-project",
                "website_url": "https://example.com",
                "normalized_domain": "example.com",
                "pages_found": 180,
                "pages_crawled": 150,
                "project": {"cms_platform": "WordPress", "website_url": "https://example.com"},
                "fix_list": {"total_fixes": 2, "high_count": 1, "medium_count": 1},
                "recommendations": [
                    {
                        "fix_id": "redirect-links",
                        "rule": "redirect_internal_links",
                        "category": "Links",
                        "issue_title": "Update redirected internal links",
                        "plain_english_explanation": "Some internal links point through a redirect before reaching the live page.",
                        "why_it_matters": "Direct links avoid unnecessary crawl hops.",
                        "priority": "high",
                        "difficulty": "medium",
                        "requires_developer": False,
                        "requires_approval": False,
                        "affected_pages": ["https://example.com/guides"],
                        "what_to_do_steps": ["Update the link target in the shared navigation."],
                        "verified_urls": [
                            {"url": "https://example.com/guides", "status_code": 200}
                        ],
                    }
                ],
            },
        ),
        EvaluationCase(
            case_id="metadata-content",
            question="Explain this in plain English and give me the safest implementation steps.",
            authority=_authority("fixture-metadata"),
            evidence={
                "release_gate_eligible": True,
                "scan_id": "fixture-metadata",
                "project_id": "fixture-project",
                "website_url": "https://shop.example.com",
                "normalized_domain": "shop.example.com",
                "pages_found": 96,
                "pages_crawled": 96,
                "project": {"cms_platform": "Shopify", "website_url": "https://shop.example.com"},
                "fix_list": {"total_fixes": 1, "medium_count": 1},
                "recommendations": [
                    {
                        "fix_id": "meta-descriptions",
                        "rule": "missing_meta_description",
                        "category": "Content",
                        "issue_title": "Add useful meta descriptions",
                        "why_it_matters": "Descriptions can improve search-result messaging.",
                        "priority": "medium",
                        "difficulty": "easy",
                        "requires_developer": False,
                        "requires_approval": False,
                        "affected_pages": ["https://shop.example.com/products/sample"],
                        "verified_urls": [
                            {"url": "https://shop.example.com/products/sample", "status_code": 200}
                        ],
                    }
                ],
            },
        ),
        EvaluationCase(
            case_id="indexability-robots",
            question="Is this safe to change myself, and how do I verify I did not block the wrong pages?",
            authority=_authority("fixture-indexability"),
            evidence={
                "release_gate_eligible": True,
                "scan_id": "fixture-indexability",
                "project_id": "fixture-project",
                "website_url": "https://docs.example.com",
                "normalized_domain": "docs.example.com",
                "pages_found": 240,
                "pages_crawled": 150,
                "project": {"cms_platform": "custom", "website_url": "https://docs.example.com"},
                "fix_list": {"total_fixes": 1, "high_count": 1},
                "recommendations": [
                    {
                        "fix_id": "robots-conflict",
                        "rule": "robots_indexability_conflict",
                        "category": "Indexability",
                        "issue_title": "Resolve conflicting indexability signals",
                        "why_it_matters": "Conflicting directives can prevent intended pages from being indexed.",
                        "priority": "high",
                        "difficulty": "hard",
                        "requires_developer": True,
                        "requires_approval": True,
                        "affected_pages": ["https://docs.example.com/reference/widget"],
                        "what_to_do_steps": [
                            "Confirm the intended indexability policy before changing robots or meta directives."
                        ],
                        "verified_urls": [
                            {"url": "https://docs.example.com/reference/widget", "status_code": 200}
                        ],
                    }
                ],
            },
        ),
        EvaluationCase(
            case_id="canonical-structured-data",
            question="Give my developer an implementation checklist with rollback and verification steps.",
            authority=_authority("fixture-technical"),
            evidence={
                "release_gate_eligible": True,
                "scan_id": "fixture-technical",
                "project_id": "fixture-project",
                "website_url": "https://tickets.example.com",
                "normalized_domain": "tickets.example.com",
                "pages_found": 410,
                "pages_crawled": 150,
                "project": {"cms_platform": "custom", "website_url": "https://tickets.example.com"},
                "fix_list": {"total_fixes": 2, "high_count": 1, "medium_count": 1},
                "recommendations": [
                    {
                        "fix_id": "canonical-template",
                        "rule": "canonical_target_mismatch",
                        "category": "Technical SEO",
                        "issue_title": "Correct canonical targets on event templates",
                        "priority": "high",
                        "difficulty": "hard",
                        "requires_developer": True,
                        "requires_approval": True,
                        "affected_pages": ["https://tickets.example.com/event/sample"],
                        "verified_urls": [
                            {"url": "https://tickets.example.com/event/sample", "status_code": 200}
                        ],
                    },
                    {
                        "fix_id": "event-schema",
                        "rule": "structured_data_missing",
                        "category": "Structured data",
                        "issue_title": "Add event structured data to the shared template",
                        "priority": "medium",
                        "difficulty": "medium",
                        "requires_developer": True,
                        "requires_approval": False,
                        "affected_pages": ["https://tickets.example.com/event/sample"],
                        "verified_urls": [
                            {"url": "https://tickets.example.com/event/sample", "status_code": 200}
                        ],
                    },
                ],
            },
        ),
        EvaluationCase(
            case_id="no-high-confidence-findings",
            question="What should I do next?",
            authority=_authority("fixture-clean"),
            evidence={
                "release_gate_eligible": True,
                "scan_id": "fixture-clean",
                "project_id": "fixture-project",
                "website_url": "https://clean.example.com",
                "normalized_domain": "clean.example.com",
                "pages_found": 48,
                "pages_crawled": 48,
                "customer_summary": "No high-confidence repair recommendations were produced by this scan.",
                "next_best_step": "Review lower-confidence observations or rescan after meaningful site changes.",
                "project": {"cms_platform": "unknown", "website_url": "https://clean.example.com"},
                "fix_list": {"total_fixes": 0, "no_high_confidence_findings": True},
                "recommendations": [],
            },
        ),
        EvaluationCase(
            case_id="follow-up-context",
            question="What about the next one?",
            authority=_authority("fixture-followup"),
            evidence={
                "release_gate_eligible": True,
                "scan_id": "fixture-followup",
                "project_id": "fixture-project",
                "website_url": "https://example.org",
                "normalized_domain": "example.org",
                "pages_found": 75,
                "pages_crawled": 75,
                "project": {"cms_platform": "WordPress", "website_url": "https://example.org"},
                "fix_list": {"total_fixes": 2, "high_count": 2},
                "recommendations": [
                    {
                        "fix_id": "links",
                        "rule": "redirect_internal_links",
                        "issue_title": "Update redirected internal links",
                        "priority": "high",
                        "affected_pages": ["https://example.org/about"],
                        "verified_urls": [
                            {"url": "https://example.org/about", "status_code": 200}
                        ],
                    },
                    {
                        "fix_id": "titles",
                        "rule": "duplicate_titles",
                        "issue_title": "Make duplicate titles unique",
                        "priority": "high",
                        "affected_pages": ["https://example.org/services"],
                        "verified_urls": [
                            {"url": "https://example.org/services", "status_code": 200}
                        ],
                    },
                ],
            },
            history=(
                {"role": "user", "content": "How do I fix the redirected links?"},
                {"role": "assistant", "content": "Update the shared navigation targets and verify they resolve directly."},
            ),
        ),
    )
