# Published paid Standard 500 evidence

Run this check for one approved, ordinary account on the paid pilot while Standard 150 stays open. It reads observations and existing workspace artifacts. The published pilot operator and the customer still perform the approved activation and browser journey. The resulting report establishes full-cap fixture execution for that named account. Public 500 admission requires the separate rollout checks in the [staged scanner runbook](staged-scan-runbook.md#named-standard-500-pilot-while-standard-150-is-open).

## Capture the prerequisites

Use the exact merged source checkout that the candidate is running. Store the field-only JSON inputs and signing key files in an external, access-controlled directory with mode 0600 on each file. Use the two authorized signing key files only on the release verifier. Never put keys, access tokens, cookies, payment details, or an unredacted browser trace in an evidence packet.

- `expected.json` holds the independently approved `source_sha`, `fingerprint`, `owner_user_id`, `grant_id`, `cohort_id`, `release_id`, `operator_id`, and reviewed `worker_config_sha256`.
- `prerequisites.json` uses `schema_version: "published_paid_500_prerequisites_v1"`, `base44_app_id`, `source_sha`, `release_fingerprint`, and `observed_at`. Make the capture after the signed activation and within 15 minutes of the browser launch. Include these sections.
  - `worker` comes from the canonical Cloud Run service and serving revision readbacks and the worker build verifier. Record `origin`, `service`, `revision`, `ready`, `source_sha`, `release_fingerprint`, `staged_config_sha256`, `pipeline_mode`, `staged_owner_ids`, `legacy_owner_ids`, `stage_target`, `stage_tag_revision`, `stage_token_audience`, `stage_queue`, `workspace_bucket`, and serving `traffic` as an array of positive traffic rows with `revision` and `percent`. The source tag maps to the same canonical revision. The worker's process defaults to monolith. A named paid request and its persisted attempt use staged execution.
  - `gateway` is the serving canonical gateway's authenticated `/health` with its service `origin`. `intake` is the V9 launcher's administrator-only `staged_runtime_status` response with the versioned `route_name` that was called. Keep their named cohort digests and the launcher expiry, and confirm the broad 500 switches are disabled. `coordinator` is the canonical admission coordinator's authenticated `/health`.
  - `pilot_snapshot` is the complete signed snapshot from `start-published-500-pilot`. Use its printed snapshot ID to obtain the exact document from the coordinator's private snapshots collection (default `scan_admission_snapshots`). Preserve the signed fields and proof. The verifier checks its HMAC against the authoritative operator key, the open barrier generation, the expected release and cohort, the named account digest, and the published launcher build.
  - `account` contains `id`, `role`, and normalized `email` from the production account read. `matching_grants` contains the complete set of matching rows found by owner or normalized email. Project each row to `id`, `owner_user_id`, `user_email`, `app_id`, `plan_id`, `has_full_access`, `access_status`, `page_cap`, `grant_source`, and the applicable grant or payment timestamp. For a Stripe grant include the non-secret `stripe_checkout_session_id`.
- Keep the published Standard 150 proof from the separate acceptance check with the release notes. This command verifies the named 500 fixture and checks that the captured coordinator barrier is open.

Run the configuration check before the browser submission.

```bash
python scanner-api/scripts/collect_published_paid_500.py \
  --expected "$evidence_dir/expected.json" \
  --prerequisites "$evidence_dir/prerequisites.json" \
  --operator-key-file "$operator_key_path" prerequisites
```

## Verify the completed browser journey and private receipts

On the published app, sign in as the approved ordinary user. Submit the owned 640-page fixture using the normal form. Refresh once while the scan is active. After the full report loads, sign out, sign in again, and reopen the exact scan from account history.

- `browser.json` uses `schema_version: "published_paid_500_browser_v1"`, `source_sha`, `owner_user_id`, `role`, `observed_at`, and `history_reopened_at`. Record `launch_url`, `history_url`, the versioned `launch_route` and `result_route`, and `displayed_page_cap`. Record each personally observed action in `launched_by_form`, `refreshed_during_progress`, `reopened_from_history`, and `reopened_after_sign_in`. Keep the response fields for `options`, initial `launch`, `saved_projection`, and `history_projection` used by the verifier. The report projections must return current verified full authority. Protect these account-scoped captures. The tool checks consistency of these observations. It does not control the browser.
- `saved-run.json` is the exact persisted ScanRun projection captured by an authorized administrator. Include the request, idempotency, project, owner and FixList identifiers, target, cap, staged mode, attempt and batch counts, terminal state and fingerprint, and timestamps. Include `authority_proof`, `release_gate_eligible`, all signed `admission_cohort_evidence_*` and `admission_acceptance_*` fields, barrier generation and claim sequence, admission mode, and the `admission_release_*` fields. The verifier checks the persisted claim signature with the coordinator's separate scan evidence key. It requires the exact claim to be reconciled as released.

```bash
python scanner-api/scripts/collect_published_paid_500.py \
  --expected "$evidence_dir/expected.json" \
  --prerequisites "$evidence_dir/prerequisites.json" \
  --operator-key-file "$operator_key_path" collect \
  --browser "$evidence_dir/browser.json" \
  --saved-run "$evidence_dir/saved-run.json" \
  --claim-key-file "$scan_evidence_key_path" \
  --output "$evidence_dir/paid-500-receipts.json"
```

The collector reads the private workspace through read-only Google Application Default Credentials. It reuses the staged receipt checks for the delivery history, producer and generation lineage, final report request, and worker memory evidence. It pins each plan, page checkpoint, and result read to those verified generations. Ten checkpoints must add exactly 50 distinct successful canonical pages each from the fixture. The final result must contain the same 500 URLs. The output contains provenance hashes and counts. It excludes the browser observations, raw grants, page URLs, proofs, and keys. A failed check exits nonzero and leaves no verified receipt.
