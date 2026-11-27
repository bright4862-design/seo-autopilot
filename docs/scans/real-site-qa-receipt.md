# Real-site QA receipt

Use this read-only collector for a completed row in the paired 20-site
register. An operator supplies an already-approved site and account scope.
The collector matches the signed claim and the customer's reopened result to
the private worker receipts for that exact attempt.

Capture only the fields below. Store the input and the existing scan evidence
signing key in private, absolute-path files with mode 0600. The verifier uses
read-only application credentials for the private workspace. The checkout
needs the approved candidate's commit in its Git history.

## Input capture

Use one JSON object with `schema_version` set to
`real_site_qa_receipt_input_v1`.

| Section | Fields to capture |
| --- | --- |
| `approved_scope` | Register `row_id` such as `S01-150`, integer `page_cap`, exact submitted HTTPS `target_url`, `path_prefix` (use `/` for whole site), and `allowed_url_prefixes` as one to eight exact HTTPS host-and-path prefixes with query strings omitted. Explicitly include any separately authorized redirect host. Include the scoped `owner_user_id`, `project_id`, timezone-bearing `authorized_from` and `authorized_until`, and the SHA-256 of the independently reviewed permission record in `authorization_reference_sha256`. |
| `worker_runtime` | The exact reviewed worker receipt identity with `source_sha`, `release_fingerprint`, `service`, `revision`, `pipeline_mode`, `staged_config_sha256`, and `staged_owner_cohort_sha256`. Copy the process mode and cohort digest verbatim from the reviewed worker receipt. The canonical paid worker reports `monolith` with the empty cohort digest. Its saved scan and plan still use the `staged` pipeline. |
| `saved_run` | The authorized operator's projection of the persisted ScanRun with scan, owner, project, request, idempotency and FixList IDs, URL, attempt and committed batch, tier, pipeline mode, terminal state, checked/planned counts, release fingerprint and timestamps. For a canonical paid worker include the run's `staged_rollout_scope: "paid"`. Include `release_gate_eligible`, the applicable authority or result-integrity proof, the persisted `admission_*` claim proof and release fields, and the cooldown publication state if present. |
| `browser` | The ordinary viewer's `owner_user_id` and `role`, the exact versioned `result_route` called, `history_url` and `history_reopened_at`. Include the field-only `projection` returned by that authenticated history read, including its access, authority, integrity and release flags, identifiers and saved `run` fields. |

Choose `approved_scope.expected_outcome` before review. Use
`complete_at_cap` when the run should check the full tier, or
`complete_queue_exhausted` when it should stop below cap because it exhausted
its queue. A worker-limited result uses `limited` and an
`expected_limit_reason` of `rate_limit`, `initial_access_limited`,
`wall_budget`, or `request_budget`. The reopened limited projection must
still verify its integrity and show the appropriate limitation. Coverage-only
limitations need a separate QA adjudication. This receipt path covers
robots-respecting runs with at least one checked URL and one committed batch.

From the repository root, run the following command after the attempt releases
its admission slot.

```bash
python scanner-api/scripts/collect_real_site_scan_receipt.py \
  --input "$private_capture" \
  --claim-key-file "$scan_evidence_key_path" \
  --output "$new_private_receipt"
```

The verifier pins the plan, cumulative batch manifests and final result to the
producer generations in the worker receipts. It binds each checked final URL
to the approved scope, refuses duplicate checked identities, and separately
counts successful HTML. A checked 404 or a non-HTML resource can be valid
technical evidence. A canonical pointing somewhere else can itself be a
finding. An out-of-scope retained page, a changed artifact, or an unconfirmed
cooldown leaves the receipt unverified.

## Record the QA result

Link the private output in `stage_receipt_evidence_ref` on the matching
`row_id`. Use its scan and source identity, planned and committed counts,
duration, inventory, checked and usable counts, terminal outcome and
rate-limit observation. Keep the private checked/discovered URL manifests and
the actual saved report reference with the QA record. The collector publishes
counts and digests without page URLs, raw browser responses, or key material.

Obtain site permission and observe the customer journey before collecting
this receipt. Record the critical and high finding reviews, lower-priority
and passed-page samples, seeded controls, duplicate checks, and the
independent review separately. Apply the existing owned-fixture and 50-site
gates in their documented release sequence.

## Verify the paired register

Use the read-only register check after recording the technical evidence and
the human review for each row. It reads the approved candidate from local
Git history, so you can run it from a separate evidence checkout.

```bash
python scanner-api/scripts/verify_real_site_qa_register.py \
  --register "$private_register_csv" \
  --evidence-dir "$private_evidence_directory" \
  --source-sha "$approved_candidate_sha" \
  --tier 150
```

Use `--tier 150` for the first Standard 150 decision and `--tier 500` for
the combined Standard 150 and 500 decision. Keep both planned rows for all
20 distinct sites in the CSV. The command checks 20 completed rows for 150
and all 40 rows for 500. It prints counts and the first blocking reason for each
missing or mismatched row. The combined check requires the same submitted URL,
scan path and allowed host-and-path scope at both caps. Each cap can use a
separately reviewed authorization window and account.

Use these existing register references for locally readable files in the
private evidence directory.

- Put the actual permission record in `current_authorization_ref`. Its
  bytes must match both the collector input and the receipt. Use the
  permission's end time in `current_authorization_expires_at`.
- Put the exact original collector input in
  `actual_owner_project_binding_evidence_ref` and its verified output in
  `stage_receipt_evidence_ref`. The input and receipt must match the same
  owner, project, attempt, candidate, cap, saved report, and reviewed scope.
- Use a JSON array of the normalized distinct checked URLs in
  `checked_url_manifest_ref`. The count and digest must match the receipt.
  Keep the discovered URL manifest, technical class evidence, findings
  review, sampling method, and seeded-control evidence in their respective
  existing file references. Mark the measured inventory and each
  independently established technical class as `verified` in its status
  field. The checker reports min/max observed discovered inventory and the
  four recorded class flags per cap.
- Record the primary reviewer and the second reviewer, enter the reviewed
  counts, and use `complete` for completed review statuses and `pass` for
  accepted verdicts. Fill only from the actual review. The checker verifies
  that every recorded critical and high group was reviewed. Sample counts
  are recorded without a minimum threshold.

In `independent_audit_evidence_ref`, retain the second reviewer's JSON
attestation with `schema_version: "real_site_qa_review_attestation_v1"`,
`row_id`, `scan_id`, `source_sha`, `primary_reviewer`,
`independent_auditor`, and `verdict`. Record the SHA-256 of the exact
receipt and permission files in `receipt_sha256` and
`authorization_sha256`. In `review_evidence_sha256` map the six existing
evidence-reference field names to the SHA-256 of each physical file.
In `reviewed_register_fields` copy the exact CSV strings for the
critical/high group and disposition counts, lower-priority and passed-page
sample counts, missed seeded defects, the four technical-class statuses,
verified inventory, and review statuses and verdicts. The contract lists
these keys in `REVIEW_FILES` and `REVIEWED_FIELDS` in the verifier.

A verified result establishes completeness and integrity of the supplied
records for the selected tier. The release owner reviews consent, the
reviewers' independence, inventory diversity, and finding accuracy using
those records. The verification digest identifies the exact register,
candidate, tier and matched evidence for that decision. The checker writes
only its report to standard output.
