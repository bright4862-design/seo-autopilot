import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { RELEASE_AUTHORITY_CONTRACT } from "../../src/lib/scanRunModel.js";

const revision = JSON.parse(readFileSync(new URL("../../data/beta-crawler-revision.json", import.meta.url), "utf8"));
const recoverySource = readFileSync(new URL("../../src/lib/scanStorageRecovery.js", import.meta.url), "utf8");

test("compact recovery and durable persistence share one release authority contract", () => {
  assert.equal(RELEASE_AUTHORITY_CONTRACT.betaRevisionFingerprint, revision.fingerprint);
  assert.equal(RELEASE_AUTHORITY_CONTRACT.scannerBuildRevision, revision.component_versions.scanner_build_revision);
  assert.equal(RELEASE_AUTHORITY_CONTRACT.archetypeClassifierVersion, revision.component_versions.archetype_classifier_version);
  assert.match(recoverySource, /import { RELEASE_AUTHORITY_CONTRACT } from "@\/lib\/scanRunModel"/);
  assert.match(recoverySource, /betaRevisionFingerprint: CURRENT_BETA_REVISION_FINGERPRINT/);
  assert.doesNotMatch(recoverySource, /52348dd1f3b77700/);
  assert.doesNotMatch(recoverySource, /const CURRENT_BETA_REVISION_FINGERPRINT =/);
});
