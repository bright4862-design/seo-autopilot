import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

import { REVIEW_ATTESTATION_VERSION } from "../../base44/functions/persistDurableScanAuthority/authoritySnapshot.js";

/**
 * The reader must accept every seal version the writer produces.
 *
 * This is the regression that shipped: the attestation moved to
 * standard_review_snapshot_hmac_v2_coverage so historical v1 rows would keep
 * verifying, and getCustomerScanResult was left pinned to v1 by an equality
 * check. New scans sealed fine and then read back as
 * 409 result_not_authoritative -- "This scan has no verified result" -- for
 * every customer, on a result that was perfectly intact.
 *
 * The earlier tests missed it because they exercised the reconstruction helpers
 * that changed, not the guard that consumes them. So this one reads the
 * endpoint source: the accepted set has to be a set, and it has to contain
 * whatever persistDurableScanAuthority is currently stamping.
 */

const SOURCE = readFileSync(
  new URL("../../base44/functions/getCustomerScanResult/entry.ts", import.meta.url),
  "utf8",
);

function acceptedSealVersions() {
  const match = SOURCE.match(/const ACCEPTED_AUTHORITY_VERSIONS[^=]*=\s*new Set\(\[([^\]]*)\]\)/);
  if (!match) return null;
  return match[1].split(",").map((entry) => entry.trim().replace(/^["']|["']$/g, "")).filter(Boolean);
}

test("the reader accepts the version the writer currently stamps", () => {
  const accepted = acceptedSealVersions();
  assert.ok(accepted, "getCustomerScanResult must declare a set of accepted seal versions");
  assert.ok(
    accepted.includes(REVIEW_ATTESTATION_VERSION),
    `getCustomerScanResult rejects ${REVIEW_ATTESTATION_VERSION}, which is what new scans are sealed with`,
  );
});

test("the reader still accepts historical v1 seals", () => {
  const accepted = acceptedSealVersions();
  assert.ok(
    accepted.includes("standard_review_snapshot_hmac_v1"),
    "historical results must stay readable",
  );
});

test("no equality check on a single seal version survives", () => {
  /** An equality check is what broke this; a set is what fixes it. */
  assert.doesNotMatch(
    SOURCE,
    /authority_seal_version !== AUTHORITY_VERSION/,
    "the seal version must be checked against the accepted set, not one constant",
  );
  assert.doesNotMatch(
    SOURCE,
    /snapshot\.version !== AUTHORITY_VERSION/,
    "snapshot identity must accept every supported seal version",
  );
});

test("the snapshot version is still bound to the row it came from", () => {
  /** Accepting a set must not mean accepting a mismatch between the two. */
  assert.match(
    SOURCE,
    /snapshot\.version !== cleanText\(run\.authority_seal_version/,
    "the rebuilt snapshot must carry the same version as the persisted row",
  );
});
