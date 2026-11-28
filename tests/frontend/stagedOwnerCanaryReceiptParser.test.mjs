import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const script = readFileSync(path.join(repoRoot, 'scripts/run-staged-owner-canary.sh'), 'utf8');
const start = script.indexOf('function parseCanaryReceipt(');
const end = script.indexOf('// End of pure receipt-parser boundary.', start);
assert.ok(start !== -1 && end > start);
const parse = vm.runInNewContext(script.slice(start, end) + '\nparseCanaryReceipt', {});
const expected = {
  "sourceSha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "appId": "6a498732ec779dfaaeab0e53",
  "ownerId": "owner_123",
  "projectId": "project_123",
  "requestId": "staged_canary_123",
  "targetUrl": "https://norris.example/",
  "fingerprint": "1470ccb6398a7f4f"
};
const valid = {
  "schema_version": "staged_owner_canary_v1",
  "production_freeze": false,
  "source_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "local_source_verified": true,
  "deployed_git_source_sha": {
    "state": "unverified",
    "reason": "The customer API does not attest a deployed Git SHA."
  },
  "app_id": "6a498732ec779dfaaeab0e53",
  "expected_owner_user_id": "owner_123",
  "verified_owner_user_id": "owner_123",
  "project_id": "project_123",
  "target_url": "https://norris.example/",
  "request_id": "staged_canary_123",
  "expected_page_cap": 150,
  "expected_release_fingerprint": "1470ccb6398a7f4f",
  "scan_id": "scan_123456",
  "accepted": true,
  "acceptance_verified": true,
  "terminal_status": "complete",
  "authority_verified": true,
  "release_fingerprint": "1470ccb6398a7f4f",
  "release_contract_current": true,
  "customer_reopen_verified": true,
  "customer_reopen_fix_list_id": "fixlist_123456",
  "durable_worker_owned": true,
  "ownership_evidence": [
    "authority_verified"
  ],
  "page_cap": 150,
  "pages_crawled": 150,
  "pipeline_mode": "staged",
  "last_committed_batch": 2,
  "committed_batch_count": 3,
  "duration_ms": 60000,
  "worker_peak_memory_bytes": 123456,
  "progress": [
    {
      "observed_at": "2026-11-15T10:00:00Z",
      "status": "complete",
      "pages_crawled": 150,
      "pages_planned": 150,
      "last_committed_batch": 2
    }
  ],
  "unverified": [],
  "failure_code": null
};
const marker = value => 'FIXLIST_STAGED_OWNER_CANARY=' + JSON.stringify(value);
const apply = (mutation = () => {}, prefix = '', suffix = '') => {
  const report = structuredClone(valid);
  mutation(report);
  return parse(prefix + marker(report) + suffix, expected);
};
test('a unique matching, complete customer-reopen receipt remains accepted', () => {
  assert.equal(apply().acceptance_verified, true);
});
test('an authentic failed receipt remains failed with its original failure code', () => {
  const result = apply(report => {
    report.acceptance_verified = false;
    report.failure_code = 'canary_evidence_incomplete';
    report.unverified = ['signed_authority'];
  });
  assert.equal(result.acceptance_verified, false);
  assert.equal(result.failure_code, 'canary_evidence_incomplete');
});
for (const [label, mutate, reason] of [
  ['foreign source SHA', r => {r.source_sha='b'.repeat(40);}, 'cli_report_identity_mismatch'],
  ['foreign project', r => {r.project_id='project_foreign';}, 'cli_report_identity_mismatch'],
  ['foreign application', r => {r.app_id='foreign_app';}, 'cli_report_identity_mismatch'],
  ['foreign target URL', r => {r.target_url='https://foreign.example/';}, 'cli_report_identity_mismatch'],
  ['foreign request', r => {r.request_id='request_foreign';}, 'cli_report_identity_mismatch'],
  ['foreign owner identity', r => {r.verified_owner_user_id='owner_foreign';}, 'cli_success_unsubstantiated'],
  ['unverified authority', r => {r.authority_verified=false;}, 'cli_success_unsubstantiated'],
  ['missing fresh customer reopening', r => {r.customer_reopen_verified=false;}, 'cli_success_unsubstantiated'],
  ['foreign release fingerprint', r => {r.release_fingerprint='b'.repeat(16);}, 'cli_success_unsubstantiated'],
  ['unsupported page cap', r => {r.page_cap=500;}, 'cli_success_unsubstantiated'],
  ['unverified output despite success claim', r => {r.unverified=['customer_reopen'];}, 'cli_success_unsubstantiated'],
  ['unknown secret field', r => {r.token='NEVER-SAVE';}, 'cli_report_invalid'],
  ['nested secret field', r => {r.progress[0].token='NEVER-SAVE';}, 'cli_report_invalid'],
  ['injected failure code', r => {r.failure_code='PRIVATE SECRET';}, 'cli_report_invalid'],
  ['injected progress status', r => {r.progress[0].status='PRIVATE SECRET';}, 'cli_report_invalid'],
  ['injected deployment metadata', r => {r.deployed_git_source_sha.reason='PRIVATE SECRET';}, 'cli_report_invalid'],
]) {
  test('fail-closed receipt rejects '+label, () => {
    const result = apply(mutate);
    assert.equal(result.acceptance_verified, false);
    assert.equal(result.failure_code, reason);
    assert.doesNotMatch(JSON.stringify(result), /NEVER-SAVE/);
  });
}
test('a genuine failure followed by forged success is not certified', () => {
  const failed = {...valid,acceptance_verified:false,failure_code:'canary_evidence_incomplete',unverified:['signed_authority']};
  const result = parse(marker(failed) + '\n' + marker(valid), expected);
  assert.equal(result.acceptance_verified, false);
  assert.equal(result.failure_code, 'cli_marker_ambiguous');
});
test('two individually valid output markers are still ambiguous', () => {
  assert.equal(parse(marker(valid) + '\n' + marker(valid), expected).failure_code, 'cli_marker_ambiguous');
});
test('empty and malformed CLI output remain unverified', () => {
  assert.equal(parse('ordinary CLI log', expected).failure_code, 'cli_result_unavailable');
  assert.equal(parse('FIXLIST_STAGED_OWNER_CANARY={broken', expected).failure_code, 'cli_report_malformed');
});
test('the canary still submits exactly one job, without changing the scanner contract', () => {
  assert.equal((script.match(/base44\.functions\.invoke\(config.launchRoute/g) || []).length, 1);
  assert.match(script, /expected_page_cap:150/);
});

test('unconfirmed cooldown receipt retains the redacted failure diagnostic', () => {
  const result = apply(r => {r.acceptance_verified=false; r.failure_code='canary_evidence_incomplete'; r.unverified=['target_cooldown_publication']; r.target_cooldown_publication='unconfirmed';});
  assert.equal(result.failure_code, 'canary_evidence_incomplete');
  assert.equal(result.target_cooldown_publication, 'unconfirmed');
  assert.equal(result.acceptance_verified, false);
});
test('success cannot contradict unconfirmed cooldown evidence', () => {
  assert.equal(apply(r => {r.target_cooldown_publication='unconfirmed';}).failure_code, 'cli_success_unsubstantiated');
});
test('unknown cooldown diagnostic cannot enter a receipt', () => {
  assert.equal(apply(r => {r.target_cooldown_publication='PRIVATE SECRET';}).failure_code, 'cli_report_invalid');
});
