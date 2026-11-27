import assert from "node:assert/strict";
import stagedRoutes from "../../../data/generated-staged-v9-routes.json" with { type: "json" };

// Fixed synthetic proofs from the V8 and V9 limited writers at 743aa8786d31c1a2417e852c40b808d687d16337.
// Regenerating them with the reader under test would hide historical HMAC changes.
const legacyProof = "cc5a8ae5d0ba3e82b25adcbf533c223f61c50069bd27f5e5f5712f15cfc66b89";
const stagedProof = "9ed1b3ebef885b8552250230f475f37922cda823dcc268329c75a3d60129efde";
const page = "https://www.funbooker.com/example";
const v8 = "getCustomerScanResultV8";

function historicalLimitedRows(staged) {
  const proof = staged ? stagedProof : legacyProof;
  const identity = { project_id: "project_hist", owner_user_id: "user_hist" };
  const scanId = "scan_hist";
  const listId = "fixlist_hist";
  const result = {
    scan_status: "inconclusive_insufficient_evidence", score_is_provisional: true,
    coverage_state: "limited_coverage", health_score: 52,
    result_integrity_version: "standard_limited_result_integrity_v5_report_evidence",
    result_integrity_proof: proof,
  };
  return {
    run: {
      ...identity, ...result, id: scanId, request_id: "request_hist", attempt_count: 1,
      normalized_domain: "funbooker.com", website_url: "https://www.funbooker.com/",
      beta_revision_fingerprint: "b36ca24b8e0f728e", status: "limited", fix_list_id: listId,
      pages_found: 150, pages_crawled: 12, release_gate_eligible: false,
      ...(staged ? { scan_mode: "standard_150", page_cap: 150, pipeline_mode: "staged" } : {}),
      limitation: "Only 12 of 150 pages were checked.", coverage_reasons: ["retained_pages_below_minimum"],
      result_integrity_sealed_at: "2026-11-15T11:22:33.000Z",
    },
    fixList: { ...identity, ...result, id: listId, scan_run_id: scanId, is_authoritative: false, total_fixes: 1 },
    fixItems: [{
      ...identity, scan_run_id: scanId, fix_list_id: listId, is_authoritative: false,
      fix_id: "title_hist", issue_title: "Missing title on one checked page", rule: "missing_title",
      priority: "medium", page_url: page, affected_pages: [page], result_integrity_proof: proof,
    }],
  };
}

async function checkLimitedRead(read, staged, expectedRoute, options) {
  const rows = historicalLimitedRows(staged);
  const { status, body, routes, result } = await read(rows, options);
  assert.equal(status, 200, body.error_code);
  assert.deepEqual(routes, [expectedRoute]);
  assert.equal(result.ok, true);
  assert.equal(result.kind, "loaded");
  assert.equal(result.result_integrity_verified, true);
  assert.equal(result.authority_verified, false);
  assert.equal(body.access, "full");
  assert.equal(body.scan_id, rows.run.id);
  assert.equal(body.fix_list_id, rows.fixList.id);
  assert.equal(body.run.status, "limited");
  assert.equal(body.authority_verified, false);
  assert.equal(body.result_integrity_verified, true);
  assert.equal(body.release_contract_current, false);
  assert.equal(body.run.release_gate_eligible, false);
  assert.equal(body.run.health_score_status, "insufficient_evidence");
  assert.equal(body.run.score_is_provisional, true);
  assert.equal(body.run.health_score, rows.run.health_score);
  assert.equal(body.run.pages_crawled, rows.run.pages_crawled);
  assert.equal(body.run.pages_found, rows.run.pages_found);
  assert.equal(body.run.limitation, rows.run.limitation);
  assert.equal(body.fixList.is_authoritative, false);
  assert.equal(body.fixList.total_fixes, 1);
  assert.deepEqual(body.fixItems.map(item => [item.fix_id, item.issue_title, item.affected_pages]),
    [["title_hist", "Missing title on one checked page", [page]]]);
  assert.equal(JSON.stringify(body).includes(rows.run.result_integrity_proof), false);

  const altered = structuredClone(rows);
  altered.fixItems[0].issue_title = "Unsigned replacement";
  const rejected = await read(altered, options);
  assert.equal(rejected.status, 409);
  assert.equal(rejected.body.error_code, "limited_result_invalid");
  assert.deepEqual(rejected.routes, [expectedRoute]);
  assert.equal(rejected.result.kind, "authority_invalid");
  assert.equal(Object.hasOwn(rejected.body, "fixItems"), false);
}

export async function checkHistoricalLimitedReopen(read) {
  const pilotRoute = stagedRoutes.functions.getCustomerScanResultV9.route_name;
  const pilot = { generation: "PUBLISHED_PILOT" };
  await checkLimitedRead(read, false, v8);
  await checkLimitedRead(read, false, pilotRoute, pilot);
  await checkLimitedRead(read, true, pilotRoute, pilot);
}
