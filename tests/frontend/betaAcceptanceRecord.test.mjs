import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

// data/beta-crawler-revision.json is the enforced freeze source — CI's
// "Verify frozen beta revision matches code" step compares it to the running
// constants. docs/beta-acceptance.md is the human-readable evidence pack that
// issue #107 requires. When those two disagree, the release record asserts a
// production validation of a build that was never validated, and every reader
// downstream inherits the wrong baseline.
const revision = JSON.parse(fs.readFileSync("data/beta-crawler-revision.json", "utf8"));
const doc = fs.readFileSync("docs/beta-acceptance.md", "utf8");

test("the acceptance record names the fingerprint that is actually frozen", () => {
  const fp = revision.fingerprint;
  assert.ok(fp, "the freeze source must carry a fingerprint");
  assert.ok(doc.includes(fp),
    `docs/beta-acceptance.md must name the frozen fingerprint ${fp}`);
});

test("the acceptance record names the classifier that is actually frozen", () => {
  const classifier = revision.component_versions.archetype_classifier_version;
  assert.ok(classifier, "the freeze source must carry a classifier version");
  assert.ok(doc.includes(classifier),
    `docs/beta-acceptance.md must name the frozen classifier ${classifier}`);
});

test("a superseded acceptance is never presented as the current baseline", () => {
  // Any fingerprint the doc mentions that is NOT the frozen one belongs to a
  // historical record and must be labelled as such, so no reader mistakes a
  // past 20-site validation for coverage of the shipping build.
  const mentioned = [...doc.matchAll(/`([0-9a-f]{16})`/g)].map((m) => m[1]);
  const stale = [...new Set(mentioned)].filter((f) => f !== revision.fingerprint);
  if (stale.length > 0) {
    assert.match(doc, /historical/i,
      `doc mentions superseded fingerprint(s) ${stale.join(", ")} and must mark them historical`);
  }
});

test("a candidate freeze is not reported as accepted", () => {
  if (revision.status !== "candidate") return; // accepted builds are covered above
  assert.match(doc, /production acceptance NOT met|No-Go on evidence/i,
    "while the freeze source says candidate, the record must not claim acceptance");
  // The freeze source is honest about what is missing; the doc must not paper over it.
  assert.equal(revision.git_commit, "", "candidate must not carry a deployed commit");
  assert.equal(revision.acceptance_report, "", "candidate must not carry an acceptance report");
});
