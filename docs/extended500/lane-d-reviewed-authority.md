# Extended 500 Lane D: reviewed evidence authority (NON-OPERATIONAL)

Issue #385. Status: **implemented and tested in isolation; NON-OPERATIONAL.**
Nothing is wired: no route, worker, Base44 function, entity, queue, billing or
customer surface imports these modules. There is **no verified Extended 500
terminal issuer**, so a valid reviewed envelope is a signed *candidate* only.
It must never mark a ScanRun complete, create FixList/FixItem rows, set
`release_gate_eligible=true` on a live record, or consume entitlement.

## Files

| File | Role |
| --- | --- |
| `scanner-api/app/extended500_reviewed_authority.py` | Python producer `build_extended500_reviewed_authority` and verifier `verify_extended500_reviewed_authority` (shared validator, same reason codes) |
| `src/lib/extended500ReviewedAuthority.js` | Pure JS verifier `verifyExtended500ReviewedAuthority` and `canonicalReviewedJson` |
| `scanner-api/tests/test_extended500_reviewed_authority.py` | Good cases, producer refusals, ~75-case adversarial battery, Python→JS parity of every refusal reason and of canonical bytes |
| `tests/frontend/extended500ReviewedAuthority.test.mjs` | JS-only adversarial battery and a Python-produced 500-page envelope verified in JS |

## Contract `extended500_reviewed_authority_v1`

Signed keys: `version`, `purpose`, `operational_status`, `identity`, `release`,
`evidence_binding`, `coverage`, `review`, `pages`, `findings`,
`fix_list_summary`; plus `proof`. Exact key sets at every level.

* **Never a promotion of the unreviewed handoff.** An
  `extended500_evidence_handoff_v1_unreviewed` envelope is refused with
  `unreviewed_handoff_not_promotable`. The reviewed envelope cites the exact
  signed handoff (`evidence_binding.handoff_proof`), and the verifier re-verifies
  that handoff with its own verifier (`verifyExtended500EvidenceHandoff`, or the
  Python port) under the separate handoff key.
* **Distinct HMAC root and purpose.** Key = `HMAC-SHA256(root, "fixlist-extended500-reviewed-authority-v1")`;
  proof = `HMAC-SHA256(key, canonical_bytes)`. Standard 150 and the unreviewed
  handoff sign with the raw secret, so a misconfigured shared root still cannot
  forge a reviewed proof (tested). Root must be >= 32 bytes and differ from the
  handoff root. Proposed secret name: `EXTENDED500_REVIEWED_AUTHORITY_SIGNING_KEY`
  (not read anywhere).
* **Canonical bytes, identical in both runtimes.** Sorted keys, no whitespace,
  ASCII-printable keys, safe integers only (no floats), well-formed strings,
  depth <= 32. Non-canonical values fail (`canonical_value_invalid`) instead of
  being coerced like the lossy legacy `stable_serialize`. Byte budget 2 MiB
  (development bound, not benchmarked) -> `byte_budget_exceeded`.
* **Identity/staleness.** Owner, project, scan, request, idempotency key,
  normalized domain and 1-based attempt must equal the fresh frozen ScanRun,
  which must be `scan_mode=extended_500`, status `crawling|reviewing`, no
  `authority_proof`, `release_gate_eligible` not true.
* **Release markers.** `release` = `{scanner_source_sha, beta_revision_fingerprint, review_version}`,
  must equal a server-owned `expected_release` AND the handoff's source pins.
  Production caller would supply `FIXLIST_WORKER_SOURCE_SHA`, the generated
  `RELEASE_FINGERPRINT` and `RELEASE_COMPONENT_VERSIONS.review_version`.
* **Pages and denominators.** `pages` = typed index `{page_id: pNNN, final_url, review_state}`
  in handoff order, 1..500 (exactly the handoff's `pages_crawled`), host equal
  to the normalized domain. `coverage` binds `pages_found`, `urls_attempted`,
  `usable_html_pages` to the handoff, and `pages_assessed`, `pages_reviewed`
  (>= 1), `pages_not_reviewed`, `review_coverage_basis_points` (floor) and
  `pages_with_findings` to the page index and findings.
* **Explicit review coverage and confidence.** `review_coverage_state` is
  `all_assessed_pages_reviewed` iff every assessed page was reviewed, else
  `bounded_sample_reviewed` (a 60-page sample is never "500 reviewed").
  Bounded samples and access/evidence-limited confidence states force
  `score_is_provisional=true`. `no_high_confidence_findings` iff zero findings
  iff `review_confidence_state=no_high_confidence_findings` (mirrors `review.py`).
* **Findings map onto the Standard 150 FixItem/FixList shape** (`fix_id`,
  `rule`, `issue_title`, `priority`, `evidence_class`, `action_priority`,
  `action_priority_score`, `canonical_action_rank`, `page_scope`,
  `page_template_family`, `page_url`, `page_count`, `evidence_status`,
  `verification_state`, `confidence_score`, `repair_fingerprint`,
  `user_status`, `repair_verification_state`), max 200. Each references >= 1
  *reviewed* page id; `page_count`/`page_url` derive from those ids. Order must
  follow the canonical Python sort key (action band, score, severity;
  `repair_shadow_calibration._sort_key`) with contiguous ranks. Unique fix ids
  and fingerprints.
* **No false "fixed".** `user_status` must be `open`, `repair_verification_state`
  `not_compared` (no cross-scan comparison authority in v1), any
  fixed/resolved/done/completed state and `completed_count != 0` ->
  `false_fix_claim`.
* **Aggregation.** `fix_list_summary` must equal the recomputed priority and
  action-band counts, `completed_count: 0`, `top_action_fix_ids` (first 3) and
  `canonical_action_fix_ids`.
* **Restricted fields.** `INTERNAL_PAGE_EVIDENCE_FIELDS` plus raw HTML/body/header
  names (and any `main_text*` key) anywhere -> `restricted_field_present`; the
  producer refuses them in its input rather than stripping.
* **Non-operational markers.** `operational_status=non_operational_no_verified_terminal_issuer`,
  `review.release_gate_eligible=false`, `review.terminal_receipt_state=not_issued`;
  any other value is refused. Valid verdicts report `operational:false,
  customer_publishable:false, release_gate_eligible:false`.

## Remaining blockers (not done here)

1. Verified Extended 500 terminal issuer (`EXTENDED500_TERMINAL_SIGNING_KEY`
   receipt) — required before any v2 could allow release eligibility.
2. Isolated Base44 500 persistence package (CAS on fresh ScanRun, idempotent
   FixList/FixItem writes, compensation, release fingerprint) — not started;
   Standard 150 `persistDurableScanAuthority*` untouched and not reused.
3. Real reviewer producing the typed `review` input for 500 pages (sampling
   policy, measured runtime/memory) and the 500 worker route.
4. Cross-scan comparison (`verified_fixed`) for 500 is out of scope.
5. Byte budget and finding caps are unbenchmarked development bounds.

## Proposed shared-file patches (for the serialized integrator only)

* `extended500-admission/README.md` / authority-gates spec: add a line under
  "Still blocked" pointing to this contract as the R4 reviewed candidate,
  non-operational until a terminal issuer exists.
* Deployment contract (when wiring): register
  `EXTENDED500_REVIEWED_AUTHORITY_SIGNING_KEY` as a distinct, worker-only secret
  that is never supplied to Standard 150 services.

## Rollback

Delete the four new files and this doc (`git revert <commit>`). No schema,
manifest, fingerprint, function package or runtime behavior changes.
