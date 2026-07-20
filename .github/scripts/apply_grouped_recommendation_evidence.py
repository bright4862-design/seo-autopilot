from __future__ import annotations

import hashlib
import json
from pathlib import Path

VERSION = "grouped_recommendation_evidence_v1_metadata_states"


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one replacement, found {count}: {old!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


review_path = "scanner-api/app/review.py"
replace_once(
    review_path,
    '''QUALITY_GATE_VERSION = "review_quality_gate_v1_evidence_complete"
ORPHAN_ASSET_EVIDENCE_VERSION = "orphan_asset_evidence_v1"''',
    f'''QUALITY_GATE_VERSION = "review_quality_gate_v1_evidence_complete"
GROUPED_RECOMMENDATION_EVIDENCE_VERSION = "{VERSION}"
ORPHAN_ASSET_EVIDENCE_VERSION = "orphan_asset_evidence_v1"''',
)
replace_once(
    review_path,
    '''    "missing_meta_description": "meta_description",
    "empty_meta_description": "meta_description",
    "malformed_meta_description": "meta_description",''',
    '''    "missing_meta_description": "meta_description",
    "empty_meta_description": "meta_description",
    "malformed_meta_description": "meta_description",
    "meta_description_unusable": "meta_description",''',
)

old_grouping = '''def build_page_pattern_findings(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for page in pages:
        url = page_evidence_url(page)
        if not url or is_non_html_page_evidence(page) or not page_has_usable_html(page):
            continue
        family = normalize_template_family(page.get("page_template_family"), url)
        canonical = clean_str(page.get("canonical") or page.get("canonical_url") or "")
        if not canonical:
            add_bucket(buckets, "canonical_missing", "canonical", family, page, "Add canonical URLs across templates", "The page does not expose a canonical URL.", "Canonical URLs help search engines consolidate duplicate and near-duplicate versions of a page.", "Ask your web person to add self-referencing canonicals to the shared template or affected pages.", "developer")
        h1_count = int_or_zero(page.get("h1_count"))
        if h1_count == 0:
            add_bucket(buckets, "missing_h1", "thin_content", family, page, "Fix missing H1 headings on templates", "The page has no main H1 heading.", "A clear H1 helps users and search engines understand the page topic.", "Add one clear H1 to the affected template or page.", "moderate")
        elif h1_count > 1:
            add_bucket(buckets, "multiple_h1", "thin_content", family, page, "Use one main page heading", "The page has more than one H1 heading.", "Multiple H1s can make the page structure less clear.", "Keep one H1 as the main page heading and make the rest H2/H3 headings.", "easy")
        missing_alt = int_or_zero(page.get("image_missing_alt_count") or page.get("missing_alt_image_count"))
        if missing_alt > 0:
            add_bucket(buckets, "image_alt_text", "image_alt_text", family, page, "Batch image descriptions on templates", f"{missing_alt} images missing alt text", "Repeated image-alt gaps are usually a shared template or CMS pattern, especially on listing or detail pages.", "Fix one representative page/template first, then roll out the same rule across the affected group.", "developer" if missing_alt >= 8 else "easy")
        metadata_state = clean_str(page.get("meta_description_state"))
        if not metadata_state:
            metadata_state = "present_valid" if clean_str(page.get("meta_description")) else "missing"
        if metadata_state == "missing":
            add_bucket(buckets, "missing_meta_description", "meta_description", family, page, "Batch missing meta descriptions on templates", "The page has no standard meta-description element.", "Search descriptions can improve how pages appear in search results.", "Add a short description that explains the page and why someone should click.", "easy")
        elif metadata_state == "present_empty":
            add_bucket(buckets, "empty_meta_description", "meta_description", family, page, "Batch empty meta descriptions on templates", "A meta-description element exists, but its content value is empty.", "An empty description gives search engines no page-specific summary to use.", "Populate the existing description field with a concise, page-specific summary.", "easy")
        elif metadata_state == "malformed":
            add_bucket(buckets, "malformed_meta_description", "meta_description", family, page, "Fix malformed meta descriptions on templates", "A meta-description element exists without a usable content attribute.", "Malformed metadata may be ignored by search engines and auditing tools.", "Output one valid meta name=\"description\" element with a non-empty content value.", "developer")

    fixes = []
    for bucket in buckets.values():
        affected = [page_evidence_url(page) for page in bucket["pages"]]
        is_group = len(set(map(clean_path, affected))) > 1
        title = page_pattern_title(bucket["rule"], bucket["family"], is_group)
        fixes.append(make_fix(
            rule=bucket["rule"],
            category=bucket["category"],
            priority="critical" if bucket["category"] == "canonical" else "high" if len(bucket["pages"]) >= 8 else "medium",
            title=title,
            explanation="Several similar pages have the same template-level issue. Fix the shared template or pattern instead of creating one task per page." if is_group else bucket["explanation"],
            why="Large sites usually have template problems. Grouping keeps the FixList focused on the highest-impact patterns." if is_group else bucket["why"],
            recommendation=bucket["recommendation"],
            affected_pages=affected,
            difficulty="developer" if (is_group and bucket["rule"] == "image_alt_text") or len(set(map(clean_path, affected))) >= 5 else bucket["difficulty"],
            source=f"page_pattern:{bucket['rule']}:{bucket['family']}",
            extra={
                "current_value": template_current_value(affected),
                "defect_summary": bucket["explanation"],
                "source_pages": dedupe_strings([clean_path(u) for u in affected if clean_path(u)])[:30],
                "page_template_family": bucket["family"],
            },
        ))
    return fixes

def add_bucket(buckets: dict[tuple[str, str], dict[str, Any]], rule: str, category: str, family: str, page: dict[str, Any], title: str, explanation: str, why: str, recommendation: str, difficulty: str) -> None:
    key = (rule, family)
    if key not in buckets:
        buckets[key] = {"rule": rule, "category": category, "family": family, "pages": [], "title": title, "explanation": explanation, "why": why, "recommendation": recommendation, "difficulty": difficulty, "current_value": explanation}
    buckets[key]["pages"].append(page)
'''

new_grouping = '''META_DESCRIPTION_STATE_CONFIG = {
    "missing": {
        "rule": "missing_meta_description",
        "count_key": "missing",
        "count_label": "missing tags",
        "explanation": "The page has no standard meta-description element.",
        "why": "Search descriptions can improve how pages appear in search results.",
        "recommendation": "Add a short description that explains the page and why someone should click.",
    },
    "present_empty": {
        "rule": "empty_meta_description",
        "count_key": "empty",
        "count_label": "empty values",
        "explanation": "A meta-description element exists, but its content value is empty.",
        "why": "An empty description gives search engines no page-specific summary to use.",
        "recommendation": "Populate the existing description field with a concise, page-specific summary.",
    },
    "malformed": {
        "rule": "malformed_meta_description",
        "count_key": "malformed",
        "count_label": "malformed elements",
        "explanation": "A meta-description element exists without a usable content attribute.",
        "why": "Malformed metadata may be ignored by search engines and auditing tools.",
        "recommendation": "Output one valid meta name=\"description\" element with a non-empty content value.",
    },
}
META_DESCRIPTION_RULE_ORDER = (
    "missing_meta_description",
    "empty_meta_description",
    "malformed_meta_description",
)


def add_metadata_bucket(buckets: dict[tuple[str, str], dict[str, Any]], family: str, page: dict[str, Any], state: str) -> None:
    config = META_DESCRIPTION_STATE_CONFIG[state]
    key = ("meta_description_unusable", family)
    if key not in buckets:
        buckets[key] = {
            "rule": "meta_description_unusable",
            "category": "meta_description",
            "family": family,
            "pages": [],
            "difficulty": "easy",
            "metadata_state_counts": {"missing": 0, "empty": 0, "malformed": 0},
            "metadata_rules": [],
        }
    bucket = buckets[key]
    bucket["pages"].append(page)
    bucket["metadata_state_counts"][config["count_key"]] += 1
    if config["rule"] not in bucket["metadata_rules"]:
        bucket["metadata_rules"].append(config["rule"])


def metadata_state_summary(counts: dict[str, Any]) -> str:
    labels = {"missing": "missing tags", "empty": "empty values", "malformed": "malformed elements"}
    return ", ".join(
        f"{int_or_zero(counts.get(key))} {label}"
        for key, label in labels.items()
        if int_or_zero(counts.get(key)) > 0
    )


def metadata_bucket_copy(bucket: dict[str, Any], is_group: bool) -> dict[str, Any]:
    family = bucket["family"]
    label = family_label(family)
    counts = dict(bucket.get("metadata_state_counts") or {})
    total = sum(int_or_zero(counts.get(key)) for key in ("missing", "empty", "malformed"))
    rules = [rule for rule in META_DESCRIPTION_RULE_ORDER if rule in set(bucket.get("metadata_rules") or [])]
    output_rule = "meta_description_unusable" if len(rules) > 1 else (rules[0] if rules else "missing_meta_description")
    if not is_group:
        state_config = next((item for item in META_DESCRIPTION_STATE_CONFIG.values() if item["rule"] == output_rule), META_DESCRIPTION_STATE_CONFIG["missing"])
        return {
            "rule": output_rule,
            "title": page_pattern_title(output_rule, family, False),
            "explanation": state_config["explanation"],
            "why": state_config["why"],
            "recommendation": state_config["recommendation"],
            "grouping_explanation": "",
            "combined_rules": [],
        }

    state_summary = metadata_state_summary(counts)
    title = f"Add usable meta descriptions to {label} pages" if len(rules) > 1 else page_pattern_title(output_rule, family, True)
    return {
        "rule": output_rule,
        "title": title,
        "explanation": f"FixList found {state_summary} across {total} {label} pages. These URLs use the same page pattern, so repair the shared metadata output instead of editing every URL separately.",
        "why": "Meta descriptions can appear beneath page titles in search results. Missing, empty, or malformed output leaves search engines to create their own snippet, which can be less specific or persuasive. Fixing the shared template improves the whole affected group.",
        "recommendation": "Repair the shared metadata template so every affected page outputs exactly one non-empty, page-specific, plain-text meta description, with a reliable fallback when the dedicated SEO field is blank.",
        "grouping_explanation": f"These {total} URLs use the {label} page pattern. One shared template correction can resolve the reported metadata states across the group.",
        "combined_rules": rules if len(rules) > 1 else [],
    }


def build_page_pattern_findings(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for page in pages:
        url = page_evidence_url(page)
        if not url or is_non_html_page_evidence(page) or not page_has_usable_html(page):
            continue
        family = normalize_template_family(page.get("page_template_family"), url)
        canonical = clean_str(page.get("canonical") or page.get("canonical_url") or "")
        if not canonical:
            add_bucket(buckets, "canonical_missing", "canonical", family, page, "Add canonical URLs across templates", "The page does not expose a canonical URL.", "Canonical URLs help search engines consolidate duplicate and near-duplicate versions of a page.", "Ask your web person to add self-referencing canonicals to the shared template or affected pages.", "developer")
        h1_count = int_or_zero(page.get("h1_count"))
        if h1_count == 0:
            add_bucket(buckets, "missing_h1", "thin_content", family, page, "Fix missing H1 headings on templates", "The page has no main H1 heading.", "A clear H1 helps users and search engines understand the page topic.", "Add one clear H1 to the affected template or page.", "moderate")
        elif h1_count > 1:
            add_bucket(buckets, "multiple_h1", "thin_content", family, page, "Use one main page heading", "The page has more than one H1 heading.", "Multiple H1s can make the page structure less clear.", "Keep one H1 as the main page heading and make the rest H2/H3 headings.", "easy")
        missing_alt = int_or_zero(page.get("image_missing_alt_count") or page.get("missing_alt_image_count"))
        if missing_alt > 0:
            add_bucket(buckets, "image_alt_text", "image_alt_text", family, page, "Batch image descriptions on templates", f"{missing_alt} images missing alt text", "Repeated image-alt gaps are usually a shared template or CMS pattern, especially on listing or detail pages.", "Fix one representative page/template first, then roll out the same rule across the affected group.", "developer" if missing_alt >= 8 else "easy")
        metadata_state = clean_str(page.get("meta_description_state"))
        if not metadata_state:
            metadata_state = "present_valid" if clean_str(page.get("meta_description")) else "missing"
        if metadata_state in META_DESCRIPTION_STATE_CONFIG:
            add_metadata_bucket(buckets, family, page, metadata_state)

    fixes = []
    for bucket in buckets.values():
        affected = [page_evidence_url(page) for page in bucket["pages"]]
        affected_count = len(set(map(clean_path, affected)))
        is_group = affected_count > 1
        metadata_counts = bucket.get("metadata_state_counts")
        if isinstance(metadata_counts, dict):
            copy = metadata_bucket_copy(bucket, is_group)
            output_rule = copy["rule"]
            title = copy["title"]
            explanation = copy["explanation"]
            why = copy["why"]
            recommendation = copy["recommendation"]
            grouping_explanation = copy["grouping_explanation"]
            combined_rules = copy["combined_rules"]
        else:
            output_rule = bucket["rule"]
            title = page_pattern_title(output_rule, bucket["family"], is_group)
            explanation = (
                f"FixList found the same issue on {affected_count} {family_label(bucket['family'])} pages: {bucket['explanation']} Fix the shared template or pattern instead of editing each URL separately."
                if is_group else bucket["explanation"]
            )
            why = (
                f"{bucket['why']} Because the issue repeats across one page pattern, a shared correction has broader impact than isolated page edits."
                if is_group else bucket["why"]
            )
            recommendation = bucket["recommendation"]
            grouping_explanation = (
                f"These {affected_count} URLs use the {family_label(bucket['family'])} page pattern. One shared template correction may resolve the issue across the group."
                if is_group else ""
            )
            combined_rules = []
            metadata_counts = {"missing": 0, "empty": 0, "malformed": 0}

        fixes.append(make_fix(
            rule=output_rule,
            category=bucket["category"],
            priority="critical" if bucket["category"] == "canonical" else "high" if len(bucket["pages"]) >= 8 else "medium",
            title=title,
            explanation=explanation,
            why=why,
            recommendation=recommendation,
            affected_pages=affected,
            difficulty="developer" if (is_group and output_rule == "image_alt_text") or affected_count >= 5 else bucket["difficulty"],
            source=f"page_pattern:{output_rule}:{bucket['family']}",
            extra={
                "current_value": metadata_state_summary(metadata_counts) if any(int_or_zero(metadata_counts.get(key)) for key in ("missing", "empty", "malformed")) else template_current_value(affected),
                "defect_summary": explanation,
                "source_pages": dedupe_strings([clean_path(u) for u in affected if clean_path(u)])[:30],
                "page_template_family": bucket["family"],
                "page_count": affected_count,
                "metadata_state_counts": metadata_counts,
                "combined_rules": combined_rules,
                "grouping_explanation": grouping_explanation,
                "grouped_recommendation_evidence_version": GROUPED_RECOMMENDATION_EVIDENCE_VERSION,
            },
        ))
    return fixes


def add_bucket(buckets: dict[tuple[str, str], dict[str, Any]], rule: str, category: str, family: str, page: dict[str, Any], title: str, explanation: str, why: str, recommendation: str, difficulty: str) -> None:
    key = (rule, family)
    if key not in buckets:
        buckets[key] = {"rule": rule, "category": category, "family": family, "pages": [], "title": title, "explanation": explanation, "why": why, "recommendation": recommendation, "difficulty": difficulty, "current_value": explanation}
    buckets[key]["pages"].append(page)
'''
replace_once(review_path, old_grouping, new_grouping)

replace_once(
    review_path,
    '''    "missing_meta_description", "empty_meta_description", "malformed_meta_description",
    "duplicate_meta_description", "missing_h1", "multiple_h1", "schema",''',
    '''    "missing_meta_description", "empty_meta_description", "malformed_meta_description",
    "meta_description_unusable", "duplicate_meta_description", "missing_h1", "multiple_h1", "schema",''',
)
replace_once(
    review_path,
    '''        "empty_meta_description": "missing_meta_description",
        "malformed_meta_description": "missing_meta_description",''',
    '''        "empty_meta_description": "missing_meta_description",
        "malformed_meta_description": "missing_meta_description",
        "meta_description_unusable": "missing_meta_description",''',
)
replace_once(
    review_path,
    '''        "scoring_model": SCORING_MODEL,
    }''',
    '''        "scoring_model": SCORING_MODEL,
        "grouped_recommendation_evidence_version": GROUPED_RECOMMENDATION_EVIDENCE_VERSION,
    }''',
)

beta_path = "scanner-api/app/beta_revision.py"
replace_once(
    beta_path,
    '''        ARCHETYPE_CLASSIFIER_VERSION,
        ORPHAN_ASSET_EVIDENCE_VERSION,''',
    '''        ARCHETYPE_CLASSIFIER_VERSION,
        GROUPED_RECOMMENDATION_EVIDENCE_VERSION,
        ORPHAN_ASSET_EVIDENCE_VERSION,''',
)
replace_once(
    beta_path,
    '''        "review_version": REVIEW_VERSION,
        "archetype_classifier_version": ARCHETYPE_CLASSIFIER_VERSION,''',
    '''        "review_version": REVIEW_VERSION,
        "grouped_recommendation_evidence_version": GROUPED_RECOMMENDATION_EVIDENCE_VERSION,
        "archetype_classifier_version": ARCHETYPE_CLASSIFIER_VERSION,''',
)

# Durable FixItem columns.
entity_path = Path("base44/entities/FixItem.jsonc")
entity = json.loads(entity_path.read_text(encoding="utf-8"))
properties = entity["properties"]
properties["metadata_state_counts"] = {
    "type": "object",
    "additionalProperties": True,
    "default": {"missing": 0, "empty": 0, "malformed": 0},
}
properties["combined_rules"] = {"type": "array", "items": {"type": "string"}, "default": []}
properties["grouping_explanation"] = {"type": "string"}
entity_path.write_text(json.dumps(entity, indent=2) + "\n", encoding="utf-8")

model_path = "src/lib/scanRunModel.js"
replace_once(
    model_path,
    '''function toArr(value) {
  return Array.isArray(value) ? value : [];
}

function modePageLimit''',
    '''function toArr(value) {
  return Array.isArray(value) ? value : [];
}

function normalizeMetadataStateCounts(value = {}) {
  const source = value && typeof value === "object" ? value : {};
  return {
    missing: Math.max(0, Number(source.missing || 0)),
    empty: Math.max(0, Number(source.empty || 0)),
    malformed: Math.max(0, Number(source.malformed || 0)),
  };
}

function modePageLimit''',
)
replace_once(
    model_path,
    '''    what_to_do_steps: toArr(fix.what_to_do_steps || fix.what_to_do || fix.fix_steps).map(toStr).slice(0, 8),
    evidence_status: toStr(fix.evidence_status),''',
    '''    what_to_do_steps: toArr(fix.what_to_do_steps || fix.what_to_do || fix.fix_steps).map(toStr).slice(0, 8),
    metadata_state_counts: normalizeMetadataStateCounts(fix.metadata_state_counts),
    combined_rules: toArr(fix.combined_rules).map(toStr).filter(Boolean).slice(0, 8),
    grouping_explanation: toStr(fix.grouping_explanation),
    evidence_status: toStr(fix.evidence_status),''',
)

Path("scanner-api/tests/test_grouped_metadata_evidence.py").write_text('''from app.extract import extract_page
from app.review import (
    GROUPED_RECOMMENDATION_EVIDENCE_VERSION,
    build_page_pattern_findings,
)


DISCOVERY = {"discovered_from": ["sitemap"], "source_pages": ["/sitemap.xml"], "link_text_samples": []}


def page(url: str, metadata_markup: str) -> dict:
    evidence = extract_page(
        f'<html><head><title>Page</title><link rel="canonical" href="{url}">{metadata_markup}</head><body><h1>Page</h1><p>Useful page evidence.</p></body></html>',
        url,
        url,
        200,
        "text/html",
        DISCOVERY,
    )
    evidence["page_template_family"] = "activity_detail"
    return evidence


def metadata_fixes(pages: list[dict]) -> list[dict]:
    return [fix for fix in build_page_pattern_findings(pages) if fix.get("category") == "meta_description"]


def test_mixed_metadata_states_become_one_evidence_specific_family_card():
    pages = [
        page("https://example.com/a", ""),
        page("https://example.com/b", ""),
        page("https://example.com/c", '<meta name="description" content="">'),
        page("https://example.com/d", '<meta name="description" content="">'),
        page("https://example.com/e", '<meta name="description" content="">'),
        page("https://example.com/f", '<meta name="description">'),
    ]

    [fix] = metadata_fixes(pages)

    assert fix["rule"] == "meta_description_unusable"
    assert fix["metadata_state_counts"] == {"missing": 2, "empty": 3, "malformed": 1}
    assert fix["combined_rules"] == [
        "missing_meta_description",
        "empty_meta_description",
        "malformed_meta_description",
    ]
    assert fix["page_count"] == 6
    assert "6 activity/detail pages" in fix["plain_english_explanation"]
    assert "2 missing tags" in fix["plain_english_explanation"]
    assert "3 empty values" in fix["plain_english_explanation"]
    assert "1 malformed elements" in fix["plain_english_explanation"]
    assert "activity/detail page pattern" in fix["grouping_explanation"]
    assert fix["grouped_recommendation_evidence_version"] == GROUPED_RECOMMENDATION_EVIDENCE_VERSION


def test_single_metadata_state_keeps_specific_rule_without_fake_combination():
    fixes = metadata_fixes([
        page("https://example.com/a", ""),
        page("https://example.com/b", ""),
    ])

    [fix] = fixes
    assert fix["rule"] == "missing_meta_description"
    assert fix["metadata_state_counts"] == {"missing": 2, "empty": 0, "malformed": 0}
    assert fix["combined_rules"] == []
    assert fix["page_count"] == 2
    assert fix["grouping_explanation"]
''', encoding="utf-8")

# Extend durable mapping and schema tests.
persistence_test = "tests/frontend/scanRunPersistence.test.mjs"
with Path(persistence_test).open("a", encoding="utf-8") as handle:
    handle.write('''\n\ntest("grouped metadata evidence persists as first-class FixItem fields", () => {\n  const fields = buildFixItemFields({\n    issue_title: "Add usable meta descriptions",\n    rule: "meta_description_unusable",\n    page_scope: "family",\n    page_template_family: "activity_detail",\n    affected_pages: ["/a", "/b", "/c"],\n    metadata_state_counts: { missing: 1, empty: 2, malformed: 0 },\n    combined_rules: ["missing_meta_description", "empty_meta_description"],\n    grouping_explanation: "These URLs use the activity/detail page pattern.",\n  }, { scanRunId: "run_grouped" });\n\n  assert.deepEqual(fields.metadata_state_counts, { missing: 1, empty: 2, malformed: 0 });\n  assert.deepEqual(fields.combined_rules, ["missing_meta_description", "empty_meta_description"]);\n  assert.equal(fields.grouping_explanation, "These URLs use the activity/detail page pattern.");\n});\n''')

meta_test = "tests/frontend/metaDescriptionGuidance.test.mjs"
replace_once(
    meta_test,
    '''const recoverySource = readFileSync(new URL("../../src/lib/scanStorageRecovery.js", import.meta.url), "utf8");''',
    '''const recoverySource = readFileSync(new URL("../../src/lib/scanStorageRecovery.js", import.meta.url), "utf8");
const fixItemEntity = JSON.parse(readFileSync(new URL("../../base44/entities/FixItem.jsonc", import.meta.url), "utf8"));''',
)
with Path(meta_test).open("a", encoding="utf-8") as handle:
    handle.write('''\n\ntest("FixItem stores grouped recommendation evidence as durable columns", () => {\n  for (const field of ["metadata_state_counts", "combined_rules", "grouping_explanation"]) {\n    assert.ok(fixItemEntity.properties[field], `FixItem missing ${field}`);\n  }\n});\n''')

Path("docs/releases/grouped-recommendation-evidence-v1.md").write_text('''# Grouped recommendation evidence v1

## Scope

- Python Review groups missing, empty, and malformed meta-description states by page-template family.
- Mixed states become one `meta_description_unusable` task with exact counts and original-rule provenance.
- Single-state groups keep their specific rule and do not invent `combined_rules`.
- All repeated page-pattern findings receive an evidence-specific grouping explanation.
- `FixItem` persists metadata counts, combined-rule provenance, and grouping rationale as first-class fields.

## Production acceptance

1. Funbooker grouped description tasks report non-zero missing/empty counts matching affected pages.
2. Saved FixItems retain the same counts and grouping copy after refresh.
3. A single-state group keeps `combined_rules: []`.
''', encoding="utf-8")

# Advance the frozen fingerprint with the new review evidence component.
revision_path = Path("data/beta-crawler-revision.json")
revision = json.loads(revision_path.read_text(encoding="utf-8"))
old_fingerprint = str(revision["fingerprint"])
components = dict(revision["component_versions"])
components["grouped_recommendation_evidence_version"] = VERSION
payload = json.dumps(components, sort_keys=True, separators=(",", ":"))
new_fingerprint = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
revision.update({
    "acceptance_report": "docs/releases/grouped-recommendation-evidence-v1.md",
    "component_versions": dict(sorted(components.items())),
    "fingerprint": new_fingerprint,
    "git_commit": "",
    "note": "Grouped recommendation evidence candidate: exact metadata-state counts, rule provenance, grouping rationale, and durable FixItem columns.",
    "recorded_at": "2026-07-20T00:00:00Z",
    "status": "candidate",
})
revision_path.write_text(json.dumps(revision, indent=2, sort_keys=True) + "\n", encoding="utf-8")

for file_name in [
    "src/lib/scanRunModel.js",
    "tests/frontend/releaseAuthorityGate.test.mjs",
    "tests/frontend/scanRunPersistence.test.mjs",
    "scanner-api/tests/test_observability.py",
]:
    target = Path(file_name)
    text = target.read_text(encoding="utf-8")
    if old_fingerprint not in text:
        raise SystemExit(f"{file_name}: old fingerprint {old_fingerprint} not found")
    target.write_text(text.replace(old_fingerprint, new_fingerprint), encoding="utf-8")

print(f"old fingerprint: {old_fingerprint}")
print(f"new fingerprint: {new_fingerprint}")
