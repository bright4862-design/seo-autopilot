import assert from "node:assert/strict";
import test from "node:test";
import { spawnSync } from "node:child_process";
import {
  buildAuthoritySnapshot,
} from "../../base44/functions/persistDurableScanAuthorityV7/authoritySnapshot.js";
import { buildAuthoritySnapshot as buildStage1LegacyAuthoritySnapshot } from "../../base44/functions/persistDurableScanAuthorityV7/authoritySnapshotStage1Legacy.js";

const SCAN_ID = "scan-stage3-v7-durable";
const PROJECT_ID = "project-stage3-v7";
const OWNER_ID = "owner-stage3-v7";
const SEALED_AT = "2026-09-21T13:40:00.000Z";

function signedPythonCompletion() {
  const result = spawnSync("python", ["tests/helpers/emitStage3SignedCompletion.py"], {
    cwd: process.cwd(),
    encoding: "utf8",
  });
  assert.equal(result.status, 0, `Python signed-completion fixture failed:\n${result.stderr}`);
  return JSON.parse(result.stdout);
}

function optionsFor(envelope, emitted, review) {
  return {
    scan: envelope.scan,
    review,
    identity: {
      scan_id: SCAN_ID,
      project_id: PROJECT_ID,
      normalized_domain: "example.com",
    },
    userId: OWNER_ID,
    now: SEALED_AT,
    identityVersion: emitted.identity_version,
  };
}

test("B27 historical/basic V7 review is not upgraded merely because non-durable B19/B21 evidence is present", () => {
  const emitted = signedPythonCompletion();
  const { envelope } = emitted;
  const historicalReview = structuredClone(envelope.review);

  // Unit/basic historical-compatible review paths can carry newly computed
  // per-fix factors/counts and an identity-agnostic delivery/score decision,
  // but without an exact-scan preview or handoff they do not claim the new
  // durable Stage-3 authority contract.
  delete historicalReview.stage3_private_preview_source;
  delete historicalReview.stage3_handoff_v2_source;

  const options = optionsFor(envelope, emitted, historicalReview);
  const expected = buildStage1LegacyAuthoritySnapshot(options);
  const actual = buildAuthoritySnapshot(options);

  assert.deepEqual(actual, expected);
  assert.equal(actual.scan.health_score_explanation?.stage3_delivery, undefined);
  assert.equal(actual.recommendations.some((fix) => fix.raw_finding?.stage3_delivery), false);
});

test("B24 an identity-bound partial Stage-3 durable claim still fails closed", () => {
  const emitted = signedPythonCompletion();
  const { envelope } = emitted;
  const partialReview = structuredClone(envelope.review);

  // Presence of an exact-scan preview is an identity-bound durable claim. Once
  // that claim exists, omitting another required B24 source must be rejected;
  // compatibility cannot turn a partial new contract into a legacy success.
  delete partialReview.stage3_handoff_v2_source;

  assert.throws(
    () => buildAuthoritySnapshot(optionsFor(envelope, emitted, partialReview)),
    /Stage3 durable delivery source is invalid or incomplete/,
  );
});
