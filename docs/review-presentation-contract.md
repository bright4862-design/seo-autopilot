# FixList review and presentation contract

This document freezes the boundary between Python Review and the customer-facing frontend before the full UI redesign.

The rule is simple:

> Python decides the SEO truth. The frontend formats and displays it.

## Authoritative record detection

A review result is authoritative when:

```json
{
  "ai_review_backend": "python_review_api",
  "python_review_fallback_used": false
}
```

For an authoritative result, the frontend must not regroup, retitle, reprioritize, reclassify, or reassign ownership.

Legacy scanner records and fallback results may still use compatibility inference.

## Top-level scan contract

The saved scan record should preserve these fields when provided:

### Identity and versions

- `ai_provider`
- `ai_review_backend`
- `python_review_fallback_used`
- `review_evidence_contract_version`
- `review_polish_version`
- `group_dedup_version`
- `scoring_model`
- `scanner_version`
- `sampling_version`
- `render_evidence_version`

### Coverage and evidence state

- `pages_crawled`
- `pages_found`
- `queued_remaining`
- `sampling_evidence`
- `scan_status`
- `review_confidence_state`
- `score_is_provisional`
- `access_evidence_state`
- `no_high_confidence_findings`
- `limitation`
- `render_evidence`

### Customer summary

- `health_score`
- `health_grade`
- `customer_summary`
- `simple_summary`
- `next_best_step`
- `website_health_report`

## Finding contract

Each recommendation may include the following groups of fields.

### Identity

- `id`
- `fix_id`
- `rule`
- `category`
- `customer_category`

### Customer-facing copy

- `title`
- `issue_title`
- `plain_english_explanation`
- `plain_english_summary`
- `why_it_matters`
- `recommendation`
- `recommended_value`
- `simple_next_step`
- `current_value`

The frontend may humanize labels, truncate long display text, and add CMS navigation help. It must not replace authoritative copy with its own SEO conclusion.

### Scope and classification

- `page_scope`
- `page_template_family`
- `page_type`
- `business_importance`
- `is_low_value_page`
- `is_important_business_page`
- `page_value_score`
- `page_value_label`
- `primary_defect_class`

Valid `page_scope` values:

- `page`
- `family`
- `cross_cutting`
- `sitewide`

Scope rules:

- cross-cutting access or server evidence uses `page_scope: "cross_cutting"` and `page_template_family: "mixed"`;
- a verified site-wide root cause uses `page_scope: "sitewide"` and an empty `page_template_family`;
- normal repeated template issues use `page_scope: "family"` and the real family;
- single-page findings use `page_scope: "page"`.

`mixed` and `sitewide` are not normal template families.

### URL evidence

- `page_url`
- `affected_pages`
- `source_pages`
- `link_text_samples`
- `url_confidence`
- `url_suspicion_reasons`
- `status_code`

The frontend may choose representative URLs for display, but it must not invent source provenance or convert crawler artifacts into confirmed broken pages.

### Confidence and verification

- `evidence_status`
- `verification_state`
- `limitation_code`
- `confidence_score`
- `evidence_confidence`
- `reach_score`
- `overall_priority_score`

Rate-limit findings must remain verification tasks:

```json
{
  "rule": "rate_limited_page",
  "page_scope": "cross_cutting",
  "page_template_family": "mixed",
  "evidence_status": "needs_verification",
  "verification_state": "needs_verification",
  "limitation_code": "rate_limit_requires_log_confirmation"
}
```

A 429 is crawler-access evidence, not automatic proof of a broken customer page.

### Workflow ownership

- `priority`
- `difficulty`
- `status`
- `who_can_do_this`
- `requires_developer`
- `requires_approval`
- `can_auto_fix`
- `what_to_do`
- `what_to_do_steps`
- `fix_steps`
- `estimated_time`
- `time_estimate`

For authoritative findings, the frontend must preserve these values.

## Priority values

Valid priorities are:

- `critical`
- `high`
- `medium`
- `low`

The stored compact action must preserve the raw priority. The UI may display both `critical` and `high` as “High impact,” but it must not change `critical` to `high` in storage.

## Empty and incomplete states

### Complete sample with no high-confidence findings

Expected signals:

```json
{
  "no_high_confidence_findings": true,
  "scan_status": "complete_no_high_confidence_findings",
  "health_grade": "No issues found in sample"
}
```

The UI must not claim the entire site is perfect. It should state that no high-confidence issues were found in the scanned sample.

### Incomplete evidence

Expected status:

```text
incomplete_evidence
```

Do not present a normal confident score.

### Mostly blocked crawl

Expected status:

```text
blocked_or_incomplete
```

The score is provisional and access must be verified.

### Partial access limitations

Expected status:

```text
complete_with_access_limitations
```

The usable findings may be shown, but the access limitation remains visible.

## Rendered evidence contract

Raw HTML remains the primary scan evidence in renderer v1.

Browser follow-up evidence:

- is bounded to a maximum of three pages;
- is informational;
- does not overwrite raw page records;
- does not suppress raw findings;
- does not change the health score;
- must not fail the main scan when the renderer fails.

Relevant site-level states:

- `raw_html_sufficient`
- `isolated_client_rendering_signal`
- `material_client_rendering_risk`

Relevant follow-up states:

- `not_needed`
- `recommended_not_run`
- `rendered_content_recovered`
- `browser_checked_no_material_delta`
- `browser_followup_failed`

## Frontend responsibilities

The frontend may:

- format labels and dates;
- select a limited number of representative URLs for display;
- provide CMS-specific navigation instructions;
- collapse or expand visual sections;
- map raw priority values to customer-facing badge labels;
- support legacy and fallback records through a clearly isolated compatibility path.

The frontend must not, for authoritative records:

- change the recommendation title;
- replace the explanation or remediation steps;
- change priority;
- change ownership or workflow status;
- infer a different template family;
- turn `false` booleans into `true`;
- convert `cross_cutting` or `sitewide` scope into a template claim;
- remove `needs_verification` from uncertain access evidence;
- resurrect scanner findings after an authoritative empty review.

## Versioning rules

Additive optional fields do not require a contract-version change.

A version must change when code:

- changes the meaning of an existing field;
- changes an enum value;
- changes the authority boundary;
- changes whether a score is provisional;
- changes whether rendered evidence can alter findings or score;
- changes cross-cutting or site-wide scope semantics.

Never silently repurpose an existing field.

## Release acceptance checklist

Before a release or full UI redesign is accepted:

- Python Review results bypass frontend regrouping;
- authoritative titles, steps, priority, owner, scope, and booleans survive storage;
- `critical` survives compact-action projection;
- legal pages can remain standard and non-low-value;
- 429 findings remain `mixed`, cross-cutting, and `needs_verification`;
- site-wide canonical findings retain family evidence without claiming one template family;
- zero-finding results remain sample-bounded;
- blocked and partial scans remain provisional;
- frontend contract tests, typecheck, lint, build, and Python regressions pass.
