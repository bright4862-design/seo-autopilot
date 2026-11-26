# Standard 150 published fixture evidence

Use the 640-page FixList fixture from the published launch form with the approved ordinary account. Keep the candidate at its merged source, and run the evidence tools from their own checkout. The tools read the scan that the customer already launched.

## During the ordinary browser run

Keep the raw observations in the private release directory. Assemble the normal source-matched prerequisites with the exact launcher, worker, gateway and stage infrastructure. Defer the task observation if the fixture has yet to run.

1. Sign in at getfixlist.com as the named ordinary account. Record the published bundle source, the account role and ID, the 150 limit shown on the form, the launcher route, and the accepted response's scan ID, request ID and cap. Record the project ID from that request. Submit the [owned fixture](https://fixlist-staged-fixture-919035207432.europe-west1.run.app/) using the site's launch button.
2. Start the operator readback within 30 seconds of the scan starting. It polls the exact ScanRun, checks the durable worker and counts persisted rows for the same account and request.
3. Refresh while the scan is in progress. Capture the verified terminal projection from the named V9 reader. Sign in again and open the same report through Recent scans. Capture that returned projection and the full history URL.

Set `SOURCE_SHA`, `EXPECTED_OWNER_USER_ID`, `EXPECTED_OPERATOR_USER_ID`, `ORDINARY_SCAN_ID`, `PROJECT_ID` and `REQUEST_ID` from the observed run and approved release. `CANDIDATE_ROOT` is the clean checkout at the published candidate source. Use the authenticated, pinned Base44 CLI and preserve its output privately.

```sh
node scripts/collect-published-150-canary.mjs render-operator \
  "$CANDIDATE_ROOT" "$PREREQUISITES_FILE" > "$NEW_OPERATOR_PAYLOAD"
"$FIXLIST_BASE44_CLI" --app-id 6a498732ec779dfaaeab0e53 exec --data-env prod \
  < "$NEW_OPERATOR_PAYLOAD" > "$NEW_OPERATOR_LOG"
```

## Assemble and verify the completed run

Create a private JSON observation with schema version `published_150_browser_readback_v1` and these fields from the actual browser session.

| Fields | Evidence to preserve |
| --- | --- |
| `source_sha`, `owner_user_id`, `role` | Published page source and authenticated ordinary customer. |
| `launch_url`, `launch_route`, `displayed_page_cap`, `launched_by_form` | Published form, exact versioned launcher, displayed 150, and observed launch by button. |
| `launch` | Fields `accepted`, `scan_id`, `request_id`, `page_cap`, `scan_mode`, `pipeline_mode` from the launch response. |
| `refreshed_during_progress`, `reopened_from_history`, `reopened_after_sign_in`, `history_url`, `history_reopened_at` | Observed browser actions and the UTC time of the history reopen. Keep screenshots or a local recording with the private evidence. |
| `result_route`, `saved_projection`, `history_projection` | Same versioned result reader for both reads. Retain response fields `success`, `access`, `authority_verified`, `release_contract_current`, `scan_id`, `fix_list_id`. Include the `run` fields `id`, `project_id`, `website_url`, `page_cap`, `pipeline_mode`, `status`, `pages_crawled`, `pages_planned`, `started_at` and `completed_at`. Full projections also supply `scan_mode` and `beta_revision_fingerprint`. The operator readback supplies those fields for the signed preview. |

Collect within 15 minutes of the terminal operator observation. Attach `ORDINARY_TASK_OBSERVATION_FILE` if the scan's live task metadata was captured. If it was missed, the receipt collector still verifies the worker and batch lineage from the private workspace, and the task-level sample remains unverified.

```sh
node scripts/collect-published-150-canary.mjs collect \
  "$CANDIDATE_ROOT" "$PREREQUISITES_FILE" \
  "$NEW_OPERATOR_LOG" "$BROWSER_OBSERVATION" "$NEW_CANARY_REPORT"
python3 scanner-api/scripts/collect_staged_scan_receipts.py \
  --canary-report "$NEW_CANARY_REPORT" --output "$NEW_RECEIPT_REPORT"
```

The receipt report must bind the plan, three committed batches, 150 distinct fixture URLs, and completion request to the same scan and attempt. The canary report records either a preview or full-access view for that account. Verify the other access path, a below-cap site, and the explicit retry behavior as separate observations before accepting the tier.
