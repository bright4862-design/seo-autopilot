#!/usr/bin/env python3
"""One-shot branch helper for the focused repair-persistence blocker fix.

This is intentionally temporary and is removed before merge. It performs exact
text replacements so the patch is reviewable and aborts if the expected source
shape has drifted.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEW_COVERAGE_VERSION = "repair_coverage_v3_unknown_mixed_scope"


def replace(path: str, old: str, new: str, *, count: int = 1) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    actual = text.count(old)
    if actual != count:
        raise SystemExit(f"{path}: expected {count} occurrence(s), found {actual}: {old[:100]!r}")
    target.write_text(text.replace(old, new), encoding="utf-8")


# Python invariant: multiple affected pages whose only partition is unknown do
# not prove a single family. They are truthfully mixed, even though the family
# breakdown has one key. A single known family remains a family repair.
replace(
    "scanner-api/app/repair_coverage.py",
    'REPAIR_COVERAGE_VERSION = "repair_coverage_v2_single_page_scope"',
    f'REPAIR_COVERAGE_VERSION = "{NEW_COVERAGE_VERSION}"',
)
replace(
    "scanner-api/app/repair_coverage.py",
    '    if scope == "mixed" and len(partitions) < 2:\n        return "mixed_scope_without_partitions"',
    '''    if scope == "mixed":\n        partition_names = {str(family).strip().lower() for family in partitions}\n        unknown_only_multi_page = (\n            page_count > 1\n            and partition_names == {UNKNOWN_FAMILY}\n        )\n        if len(partitions) < 2 and not unknown_only_multi_page:\n            return "mixed_scope_without_partitions"''',
)

# JavaScript independent invariant mirrors the same truth rule.
replace(
    "base44/functions/persistDurableScanAuthority/repairInvariants.js",
    '  if (scope === "mixed" && Object.keys(partitions).length < 2) return "mixed_scope_without_partitions";',
    '''  if (scope === "mixed") {\n    const partitionNames = new Set(Object.keys(partitions).map((family) => String(family || "").trim().toLowerCase()));\n    const unknownOnlyMultiPage = pageCount > 1 && partitionNames.size === 1 && partitionNames.has("unknown");\n    if (Object.keys(partitions).length < 2 && !unknownOnlyMultiPage) return "mixed_scope_without_partitions";\n  }''',
)

# Durable authority must preserve the producer's truthful scope instead of
# coercing mixed to page (which would immediately lie for 17/22-page repairs).
replace(
    "base44/functions/persistDurableScanAuthority/authoritySnapshot.js",
    '  const scope = ["page", "family", "cross_cutting", "sitewide"].includes(String(fix?.page_scope || ""))',
    '  const scope = ["page", "family", "mixed", "cross_cutting", "sitewide"].includes(String(fix?.page_scope || ""))',
)
replace(
    "base44/entities/FixItem.jsonc",
    '        "family",\n        "cross_cutting",',
    '        "family",\n        "mixed",\n        "cross_cutting",',
)

# Once canonical-v2 synthesis begins, failure is a failed review contract, not
# permission to publish a different legacy repair collection.
replace(
    "scanner-api/app/repair_contract_v2.py",
    'from .repair_shadow_calibration import build_calibrated_shadow_review_analysis\n\n\ndef _diagnostic_count',
    '''from .repair_shadow_calibration import build_calibrated_shadow_review_analysis\n\n\nclass CanonicalRepairContractError(RuntimeError):\n    """Canonical-v2 synthesis was attempted but could not produce one complete snapshot."""\n\n\ndef _diagnostic_count''',
)
replace(
    "scanner-api/app/repair_contract_v2.py",
    '        emit("canonical_repair_contract_absent", severity="WARNING", reason="proposed_fixes_missing")\n        return review_result',
    '        emit("canonical_repair_contract_absent", severity="WARNING", reason="proposed_fixes_missing")\n        raise CanonicalRepairContractError("canonical repair synthesis did not produce a list")',
)
replace(
    "scanner-api/app/repair_contract_v2.py",
    '            emit("canonical_repair_contract_absent", severity="WARNING", reason="proposed_fix_not_object", canonical_action_rank=rank)\n            return review_result',
    '            emit("canonical_repair_contract_absent", severity="WARNING", reason="proposed_fix_not_object", canonical_action_rank=rank)\n            raise CanonicalRepairContractError("canonical repair synthesis produced a non-object repair")',
)
replace(
    "scanner-api/app/repair_contract_v2.py",
    '''            emit(\n                "canonical_repair_invariant_rejected",\n                severity="WARNING",\n                **_safe_repair_diagnostic(canonical_fix, failed_invariant, rank=rank),\n            )\n            return review_result''',
    '''            emit(\n                "canonical_repair_invariant_rejected",\n                severity="WARNING",\n                **_safe_repair_diagnostic(canonical_fix, failed_invariant, rank=rank),\n            )\n            raise CanonicalRepairContractError(f"canonical repair invariant rejected: {failed_invariant}")''',
)
replace(
    "scanner-api/app/repair_contract_v2.py",
    '''        emit(\n            "canonical_repair_contract_absent",\n            severity="WARNING",\n            reason="persistence_candidate_rejected",\n            validation_code=str(validation.get("code") or validation.get("reason") or "")[:160],\n            canonical_fix_count=len(canonical_items),\n        )\n        return review_result''',
    '''        emit(\n            "canonical_repair_contract_absent",\n            severity="WARNING",\n            reason="persistence_candidate_rejected",\n            validation_code=str(validation.get("code") or validation.get("reason") or "")[:160],\n            canonical_fix_count=len(canonical_items),\n        )\n        raise CanonicalRepairContractError("canonical repair persistence candidate was rejected")''',
)

# Base44 independently rejects a partial/invalid attempted canonical contract.
# Reviews that contain no v2 markers at all retain the historical legacy path.
replace(
    "base44/functions/persistDurableScanAuthority/authoritySnapshot.js",
    '    ["coverage_authority_version", Boolean(text(coverageAssessment(review).coverage_authority_version, 160))],\n    // Re-derived here, not trusted.',
    '    ["coverage_authority_version", Boolean(text(coverageAssessment(review).coverage_authority_version, 160))],\n    ["canonical_repair_contract", canonicalReviewIsAbsentOrValid(review)],\n    // Re-derived here, not trusted.',
)
replace(
    "base44/functions/persistDurableScanAuthority/authoritySnapshot.js",
    'export function buildAuthoritySnapshot({ scan, review, identity, userId, now = new Date().toISOString() }) {\n  const firstPage = firstArray([scan?.crawled_pages, scan?.pages, scan?.scanned_pages])[0] || {};',
    '''export function buildAuthoritySnapshot({ scan, review, identity, userId, now = new Date().toISOString() }) {\n  const firstPage = firstArray([scan?.crawled_pages, scan?.pages, scan?.scanned_pages])[0] || {};\n  if (!canonicalReviewIsAbsentOrValid(review)) {\n    throw new Error("canonical repair contract is invalid");\n  }''',
)
replace(
    "base44/functions/persistDurableScanAuthority/authoritySnapshot.js",
    '''function canonicalReviewRequested(review) {\n  return Boolean(\n    review?.repair_contract_version === REPAIR_CONTRACT_V2\n    && review?.repair_snapshot_contract_version === REPAIR_CONTRACT_V2\n    && review?.repair_snapshot_contract_complete === true\n    && review?.repair_priority_model_version === REPAIR_PRIORITY_MODEL_V2\n    && Array.isArray(review?.canonical_repairs),\n  );\n}\n\nfunction canonicalAuthorityFixesValid(fixes) {''',
    '''function canonicalReviewRequested(review) {\n  return Boolean(\n    review?.repair_contract_version === REPAIR_CONTRACT_V2\n    && review?.repair_snapshot_contract_version === REPAIR_CONTRACT_V2\n    && review?.repair_snapshot_contract_complete === true\n    && review?.repair_priority_model_version === REPAIR_PRIORITY_MODEL_V2\n    && Array.isArray(review?.canonical_repairs),\n  );\n}\n\nfunction canonicalReviewAttempted(review) {\n  return Boolean(\n    review?.repair_contract_version !== undefined\n    || review?.repair_snapshot_contract_version !== undefined\n    || review?.repair_snapshot_contract_complete !== undefined\n    || review?.repair_priority_model_version !== undefined\n    || review?.canonical_repairs !== undefined\n  );\n}\n\nfunction canonicalReviewIsAbsentOrValid(review) {\n  if (!canonicalReviewAttempted(review)) return true;\n  if (!canonicalReviewRequested(review)) return false;\n  const mapped = suppressAggregateCoveredPageFixes(\n    review.canonical_repairs.slice(0, MAX_AUTHORITY_FIXES).map(toAuthorityFix),\n  );\n  return canonicalAuthorityFixesValid(mapped);\n}\n\nfunction canonicalAuthorityFixesValid(fixes) {''',
)

# Python regressions: exact Tiqets cardinalities + malformed named-family mixed.
replace(
    "scanner-api/tests/test_repair_scope_partitions.py",
    '''from app.repair_coverage import (\n    REPAIR_COVERAGE_VERSION,\n    normalize_repair_scope,\n)''',
    '''from app.repair_coverage import (\n    REPAIR_COVERAGE_VERSION,\n    first_failed_repair_invariant,\n    normalize_repair_scope,\n)''',
)
replace(
    "scanner-api/tests/test_repair_scope_partitions.py",
    '''def test_one_unknown_affected_page_is_page_scoped_not_mixed():\n    """A single unknown partition cannot truthfully be a mixed repair."""\n    fix = normalize_repair_scope(\n        {\n            "rule": "sitemap_redirect",\n            "page_scope": "mixed",\n            "page_template_family": "mixed",\n            "affected_pages": ["/"],\n            "page_count": 1,\n            "family_breakdown": {"unknown": 1},\n            "representative_pages_by_family": {"unknown": "/"},\n        },\n        [],\n    )\n\n    assert fix["page_scope"] == "page"\n    assert fix["page_template_family"] == "unknown"\n    assert fix["page_count"] == 1\n    assert fix["family_breakdown"] == {"unknown": 1}\n''',
    '''def test_one_unknown_affected_page_is_page_scoped_not_mixed():\n    """A single unknown partition cannot truthfully be a mixed repair."""\n    fix = normalize_repair_scope(\n        {\n            "rule": "sitemap_redirect",\n            "page_scope": "mixed",\n            "page_template_family": "mixed",\n            "affected_pages": ["/"],\n            "page_count": 1,\n            "family_breakdown": {"unknown": 1},\n            "representative_pages_by_family": {"unknown": "/"},\n        },\n        [],\n    )\n\n    assert fix["page_scope"] == "page"\n    assert fix["page_template_family"] == "unknown"\n    assert fix["page_count"] == 1\n    assert fix["family_breakdown"] == {"unknown": 1}\n\n\n@pytest.mark.parametrize("page_count", [22, 17])\ndef test_tiqets_unknown_only_multi_page_repairs_are_valid_mixed_scope(page_count):\n    """Exact cardinalities reproduced from the Tiqets production blocker."""\n    affected = [f"https://www.tiqets.com/unknown/{i}" for i in range(page_count)]\n    fix = normalize_repair_scope(\n        {"rule": "missing_h1", "affected_pages": affected},\n        [],\n    )\n\n    assert fix["page_scope"] == "mixed"\n    assert fix["page_template_family"] == "mixed"\n    assert fix["page_count"] == page_count\n    assert fix["family_breakdown"] == {"unknown": page_count}\n    assert len(fix["affected_pages"]) == page_count\n    assert first_failed_repair_invariant(fix) == ""\n\n\ndef test_mixed_scope_with_one_known_family_still_fails_closed():\n    malformed = {\n        "page_scope": "mixed",\n        "page_template_family": "mixed",\n        "affected_pages": ["/a", "/b"],\n        "page_count": 2,\n        "family_breakdown": {"product_page": 2},\n        "representative_pages_by_family": {"product_page": "/a"},\n        "affected_reported": 2,\n        "affected_observed": 2,\n        "affected_eligible": 2,\n        "indexable_affected": 0,\n    }\n    assert first_failed_repair_invariant(malformed) == "mixed_scope_without_partitions"\n''',
)

# Python canonical contract no longer silently returns legacy on invalid v2.
replace(
    "scanner-api/tests/test_repair_contract_v2.py",
    'from app.repair_contract_v2 import apply_canonical_repair_contract',
    'import pytest\n\nfrom app.repair_contract_v2 import CanonicalRepairContractError, apply_canonical_repair_contract',
)
replace(
    "scanner-api/tests/test_repair_contract_v2.py",
    '''def test_invalid_duplicate_fix_ids_fail_closed_to_legacy_review():\n    duplicate = _fix("same-id", "internal_link_redirect", "high", ["https://example.com/a"])\n    review = {"recommendations": [duplicate, {**duplicate}], "cleaned_fixes": [duplicate, {**duplicate}]}\n    scan = {"crawled_pages": [_page("https://example.com/a")]}\n\n    result = apply_canonical_repair_contract(review, scan)\n\n    assert "repair_contract_version" not in result\n    assert "canonical_repairs" not in result\n    assert result == review\n''',
    '''def test_invalid_duplicate_fix_ids_fail_closed_instead_of_publishing_legacy():\n    duplicate = _fix("same-id", "internal_link_redirect", "high", ["https://example.com/a"])\n    review = {"recommendations": [duplicate, {**duplicate}], "cleaned_fixes": [duplicate, {**duplicate}]}\n    scan = {"crawled_pages": [_page("https://example.com/a")]}\n\n    with pytest.raises(CanonicalRepairContractError):\n        apply_canonical_repair_contract(review, scan)\n''',
)

# Independent Base44 regression for the same Tiqets shape and no legacy fallback.
replace(
    "tests/frontend/repairCoverageInvariants.test.mjs",
    '''test("mixed scope must actually carry partitions", () => {\n  assert.equal(\n    firstFailedRepairInvariant(repair({ page_scope: "mixed", page_template_family: "mixed" })),\n    "mixed_scope_without_partitions",\n  );\n});''',
    '''test("mixed scope must actually carry partitions", () => {\n  assert.equal(\n    firstFailedRepairInvariant(repair({ page_scope: "mixed", page_template_family: "mixed" })),\n    "mixed_scope_without_partitions",\n  );\n});\n\ntest("Tiqets all-unknown multi-page evidence is a valid mixed scope", () => {\n  const affected = Array.from({ length: 22 }, (unused, index) => `/unknown/${index}`);\n  const tiqets = repair({\n    page_scope: "mixed",\n    page_template_family: "mixed",\n    affected_pages: affected,\n    page_count: 22,\n    family_breakdown: { unknown: 22 },\n    representative_pages_by_family: { unknown: "/unknown/0" },\n    affected_reported: 22,\n    affected_observed: 22,\n    affected_eligible: 22,\n    checked_eligible: null,\n    indexable_affected: 0,\n    indexable_checked_eligible: null,\n  });\n  assert.equal(firstFailedRepairInvariant(tiqets), "");\n  assert.equal(repairCoverageIsValid(tiqets), true);\n});''',
)
replace(
    "tests/frontend/repairCoverageInvariants.test.mjs",
    '''test("canonical v2 authority validates and seals canonical repairs, not stale legacy recommendations", () => {''',
    '''test("attempted malformed canonical v2 is rejected instead of falling back to legacy", () => {\n  const validLegacy = repair();\n  const malformedCanonical = {\n    ...repair(),\n    fix_id: "canonical-bad",\n    repair_contract_version: "repair_contract_v2_shadow_calibrated",\n    repair_priority_model_version: "repair_priority_v2_technical_severity",\n    base_severity: "high",\n    evidence_class: "confirmed_problem",\n    action_priority: "fix_first",\n    canonical_action_rank: 1,\n    // Missing repair_fingerprint makes the attempted canonical contract invalid.\n    repair_identity_version: "repair_identity_v1",\n  };\n  const review = {\n    ...authoritativeReview([validLegacy]),\n    repair_contract_version: "repair_contract_v2_shadow_calibrated",\n    repair_snapshot_contract_version: "repair_contract_v2_shadow_calibrated",\n    repair_snapshot_contract_complete: true,\n    repair_priority_model_version: "repair_priority_v2_technical_severity",\n    canonical_repairs: [malformedCanonical],\n  };\n  assert.equal(firstFailedAuthorityPredicate(AUTHORITATIVE_SCAN, review), "canonical_repair_contract");\n  assert.throws(() => buildAuthoritySnapshot({\n    scan: { ...AUTHORITATIVE_SCAN, website_url: "https://example.com" },\n    review,\n    identity: { scan_id: "scan-bad", project_id: "project-1", normalized_domain: "example.com" },\n    userId: "owner-1",\n  }), /canonical repair contract is invalid/);\n});\n\ntest("canonical v2 authority preserves Tiqets mixed scope and ignores stale legacy recommendations", () => {\n  const legacyImpossible = repair({ page_count: 0, family_breakdown: {}, representative_pages_by_family: {} });\n  const affected = Array.from({ length: 22 }, (unused, index) => `/unknown/${index}`);\n  const canonical = {\n    ...repair(),\n    fix_id: "tiqets-unknown-mixed",\n    page_scope: "mixed",\n    page_template_family: "mixed",\n    affected_pages: affected,\n    page_count: 22,\n    family_breakdown: { unknown: 22 },\n    representative_pages_by_family: { unknown: "/unknown/0" },\n    affected_reported: 22,\n    affected_observed: 22,\n    affected_eligible: 22,\n    checked_eligible: null,\n    indexable_affected: 0,\n    indexable_checked_eligible: null,\n    repair_contract_version: "repair_contract_v2_shadow_calibrated",\n    repair_priority_model_version: "repair_priority_v2_technical_severity",\n    base_severity: "high",\n    evidence_class: "confirmed_problem",\n    action_priority: "fix_first",\n    priority_reason: "22 checked pages are affected.",\n    canonical_action_rank: 1,\n    repair_identity_version: "repair_identity_v1",\n    repair_fingerprint: "tiqets-mixed-fingerprint",\n  };\n  const review = {\n    ...authoritativeReview([legacyImpossible]),\n    repair_contract_version: "repair_contract_v2_shadow_calibrated",\n    repair_snapshot_contract_version: "repair_contract_v2_shadow_calibrated",\n    repair_snapshot_contract_complete: true,\n    repair_priority_model_version: "repair_priority_v2_technical_severity",\n    canonical_repairs: [canonical],\n  };\n  assert.equal(firstFailedAuthorityPredicate(AUTHORITATIVE_SCAN, review), "");\n  const snapshot = buildAuthoritySnapshot({\n    scan: { ...AUTHORITATIVE_SCAN, website_url: "https://www.tiqets.com/", pages_found: 5000, pages_crawled: 150 },\n    review,\n    identity: { scan_id: "scan-tiqets", project_id: "project-1", normalized_domain: "tiqets.com" },\n    userId: "owner-1",\n    now: "2026-08-25T00:00:00.000Z",\n  });\n  assert.equal(snapshot.recommendations.length, 1);\n  assert.equal(snapshot.recommendations[0].fix_id, "tiqets-unknown-mixed");\n  assert.equal(snapshot.recommendations[0].page_scope, "mixed");\n});\n\ntest("canonical v2 authority validates and seals canonical repairs, not stale legacy recommendations", () => {''',
)

# Candidate release identity must move with the repair-coverage semantics.
revision_path = ROOT / "data/beta-crawler-revision.json"
revision = json.loads(revision_path.read_text(encoding="utf-8"))
components = dict(revision.get("component_versions") or {})
components["repair_coverage_version"] = NEW_COVERAGE_VERSION
payload = json.dumps(components, sort_keys=True, separators=(",", ":"))
revision["component_versions"] = components
revision["fingerprint"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
revision["status"] = "candidate"
revision["git_commit"] = ""
revision["acceptance_report"] = ""
revision["recorded_at"] = datetime.now(timezone.utc).isoformat()
revision["note"] = (
    "Production persistence recovery candidate: multi-page all-unknown repair evidence remains truthful mixed scope; "
    "attempted malformed canonical v2 fails closed instead of publishing legacy repairs. Tiqets acceptance pending."
)
revision_path.write_text(json.dumps(revision, indent=2, sort_keys=True) + "\n", encoding="utf-8")

print(revision["fingerprint"])
