import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const dispatcher = readFileSync("base44/functions/startStandardScanJobV3/entry.ts", "utf8");
const scanRunSchema = JSON.parse(readFileSync("base44/entities/ScanRun.jsonc", "utf8"));
const worker = readFileSync("scanner-api/app/main.py", "utf8");
const workerHelpers = readFileSync("scanner-api/app/scan_job.py", "utf8");
const authority = readFileSync("base44/functions/persistDurableScanAuthorityV3/entry.ts", "utf8");
const limited = readFileSync("base44/functions/persistLimitedScanResultV3/entry.ts", "utf8");

test("server derives owner robots policy from the owned BusinessProject, never browser policy intent", () => {
  assert.match(dispatcher, /site_owner_attestation/);
  assert.match(dispatcher, /owner_or_manager/);
  assert.match(dispatcher, /owner_attested_robots_override/);
  assert.match(dispatcher, /respect_robots_txt/);
  assert.match(dispatcher, /context\.project|project\.project/);
  assert.doesNotMatch(dispatcher, /body\.owner_attested_robots_override\s*===\s*true/);
  assert.doesNotMatch(dispatcher, /body\.respect_robots_txt\s*===\s*false/);
});

test("new ScanRuns freeze the server-derived robots policy and task dispatch reuses the frozen pair", () => {
  assert.match(dispatcher, /respect_robots_txt:\s*robotsPolicy\.respect_robots_txt/);
  assert.match(dispatcher, /owner_attested_robots_override:\s*robotsPolicy\.owner_attested_robots_override/);
  assert.match(dispatcher, /site_ownership_answer:\s*robotsPolicy\.site_ownership_answer/);
  assert.match(dispatcher, /respect_robots_txt:\s*scanRobotsPolicy\.respect_robots_txt/);
  assert.match(dispatcher, /owner_attested_robots_override:\s*scanRobotsPolicy\.owner_attested_robots_override/);
});

test("ScanRun schema persists the historical ownership policy used for that exact run", () => {
  assert.equal(scanRunSchema.properties.respect_robots_txt.type, "boolean");
  assert.equal(scanRunSchema.properties.owner_attested_robots_override.type, "boolean");
  assert.deepEqual(scanRunSchema.properties.site_ownership_answer.enum, ["", "owner_or_manager", "not_owner"]);
  assert.equal(scanRunSchema.properties.site_ownership_policy_version.type, "string");
});

test("worker accepts only the two valid policy pairs and activates override only for the owner pair", () => {
  assert.match(worker, /owner_attested_robots_override:\s*bool\s*=\s*False/);
  assert.match(worker, /validate_robots_policy_pair|valid_robots_policy_pair/);
  assert.match(worker, /owner_robots_override\(payload\.owner_attested_robots_override\)/);
  assert.doesNotMatch(worker, /Standard scans must respect robots\.txt/);
  assert.match(worker, /"respect_robots_txt":\s*payload\.respect_robots_txt/);
  assert.match(worker, /"owner_attested_robots_override":\s*payload\.owner_attested_robots_override/);
});

test("durable task identity rejects a robots-policy mismatch with its ScanRun", () => {
  assert.match(workerHelpers, /respect_robots_txt/);
  assert.match(workerHelpers, /owner_attested_robots_override/);
  assert.match(workerHelpers, /identity_matches/);
});

test("both authoritative and limited persistence reject a worker result whose robots policy differs from the ScanRun", () => {
  for (const source of [authority, limited]) {
    assert.match(source, /respect_robots_txt/);
    assert.match(source, /owner_attested_robots_override/);
    assert.match(source, /robots.*policy|policy.*robots/i);
  }
});
