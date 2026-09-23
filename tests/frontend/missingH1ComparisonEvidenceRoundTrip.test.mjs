import assert from "node:assert/strict";
import test from "node:test";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { webcrypto } from "node:crypto";

import { buildAuthoritySnapshot } from "../../base44/functions/persistDurableScanAuthorityV8/authoritySnapshot.js";
import { authorityRowsFromSnapshot } from "../../base44/functions/persistDurableScanAuthorityV8/authorityRows.js";
import { authoritySnapshotFromRows } from "../../base44/functions/getCustomerScanResultV8/projection.js";
import { authoritySnapshotFromRows as grokAuthoritySnapshotFromRows } from "../../base44/functions/grokChat/authoritySnapshot.js";
import {
  createAuthoritySeal,
  verifyAuthoritySeal,
} from "../../base44/functions/persistDurableScanAuthorityV8/authoritySeal.js";

const OWNER = "owner-stage3-v7";
const PROJECT = "project-stage3-v7";
const EVIDENCE_VERSION = "scan_comparison_evidence_v1_missing_h1";
const RULE_VERSION = "missing_h1_rule_v1_usable_html_h1_count_zero";
const PROFILE_VERSION = "missing_h1_comparison_v1_exact_affected_pages";
const URL_IDENTITY = "evidence_url_identity_v2_published_route";

function emit() {
  const result = spawnSync("python", ["tests/helpers/scanComparisonAuthorityBridge.py"], {
    encoding: "utf8",
    input: JSON.stringify({ action: "emit", scan_id: "comparison-evidence-roundtrip", mode: "stable" }),
  });
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}

function missingH1Evidence({ findingPresent = false } = {}) {
  return {
    version: EVIDENCE_VERSION,
    rule: "missing_h1",
    rule_definition_version: RULE_VERSION,
    comparison_profile_version: PROFILE_VERSION,
    evidence_url_identity_version: URL_IDENTITY,
    observation_count: 1,
    evaluated_page_count: 1,
    finding_present_count: findingPresent ? 1 : 0,
    finding_absent_count: findingPresent ? 0 : 1,
    observations: [{
      page_url: "https://example.com/products/a",
      status_code: 200,
      content_type: "text/html",
      page_evidence_class: "usable_html",
      indexable: true,
      robots: "",
      h1_count: findingPresent ? 0 : 1,
      evaluated: true,
      applicable: true,
      finding_present: findingPresent,
    }],
  };
}

async function persistedWithEvidence(evidence) {
  const emitted = emit();
  const review = structuredClone(emitted.envelope.review);
  if (evidence !== undefined) review.comparison_evidence = structuredClone(evidence);
  else delete review.comparison_evidence;
  const snapshot = buildAuthoritySnapshot({
    scan: emitted.envelope.scan,
    review,
    identity: {
      scan_id: "comparison-evidence-roundtrip",
      project_id: PROJECT,
      normalized_domain: "example.com",
    },
    userId: OWNER,
    now: "2026-09-23T20:30:00.000Z",
    identityVersion: emitted.identity_version,
  });
  const proof = await createAuthoritySeal(snapshot, emitted.secret, webcrypto);
  const rows = authorityRowsFromSnapshot(snapshot, {
    fixListId: "list-comparison-evidence-roundtrip",
    ownerUserId: OWNER,
    proof,
  });
  const persisted = JSON.parse(JSON.stringify({
    run: { ...rows.scanRun, id: "comparison-evidence-roundtrip", project_id: PROJECT },
    fixList: { ...rows.fixList, id: "list-comparison-evidence-roundtrip" },
    fixItems: rows.fixItems.map((item, index) => ({ ...item, id: `comparison-evidence-${index}` })),
    userId: OWNER,
  }));
  return { snapshot, proof, secret: emitted.secret, persisted };
}

test("missing-H1 comparison evidence survives signed V8 persistence and reconstruction", async () => {
  const evidence = missingH1Evidence();
  const data = await persistedWithEvidence(evidence);

  assert.deepEqual(data.snapshot.scan.comparison_evidence, evidence);
  assert.deepEqual(data.persisted.run.comparison_evidence, evidence);

  const restored = authoritySnapshotFromRows(data.persisted);
  assert.deepEqual(restored, data.snapshot);
  assert.equal(await verifyAuthoritySeal(restored, data.secret, data.proof, webcrypto), true);

  const grokRestored = grokAuthoritySnapshotFromRows({ ...data.persisted, scan: data.persisted.run });
  assert.deepEqual(grokRestored, data.snapshot);
  assert.equal(await verifyAuthoritySeal(grokRestored, data.secret, data.proof, webcrypto), true);
});

test("historical authority snapshots without comparison evidence keep their exact shape", async () => {
  const data = await persistedWithEvidence(undefined);
  assert.equal(Object.hasOwn(data.snapshot.scan, "comparison_evidence"), false);
  assert.equal(Object.hasOwn(data.persisted.run, "comparison_evidence"), false);

  const restored = authoritySnapshotFromRows(data.persisted);
  assert.deepEqual(restored, data.snapshot);
  assert.equal(await verifyAuthoritySeal(restored, data.secret, data.proof, webcrypto), true);
});

test("malformed persisted comparison evidence fails reconstruction closed", async () => {
  const data = await persistedWithEvidence(missingH1Evidence());
  data.persisted.run.comparison_evidence.observations[0].h1_count = 0;
  assert.throws(
    () => authoritySnapshotFromRows(data.persisted),
    /comparison.*inconsistent|Missing-H1 comparison evaluated state is inconsistent/i,
  );
});

test("coherently changed persisted comparison evidence cannot retain the original authority proof", async () => {
  const data = await persistedWithEvidence(missingH1Evidence());
  const changed = data.persisted.run.comparison_evidence;
  changed.observations[0].h1_count = 0;
  changed.observations[0].finding_present = true;
  changed.finding_present_count = 1;
  changed.finding_absent_count = 0;

  const rebuilt = authoritySnapshotFromRows(data.persisted);
  assert.notDeepEqual(rebuilt, data.snapshot);
  assert.equal(await verifyAuthoritySeal(rebuilt, data.secret, data.proof, webcrypto), false);
});

test("writer and reader use the same missing-H1 evidence sanitizer contract", () => {
  const writer = readFileSync(
    "base44/functions/persistDurableScanAuthorityV8/comparisonEvidence.js",
    "utf8",
  );
  const reader = readFileSync(
    "base44/functions/getCustomerScanResultV8/comparisonEvidence.js",
    "utf8",
  );
  const grok = readFileSync(
    "base44/functions/grokChat/comparisonEvidence.js",
    "utf8",
  );
  assert.equal(reader, writer);
  assert.equal(grok, writer);
});
