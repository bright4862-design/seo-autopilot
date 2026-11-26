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
