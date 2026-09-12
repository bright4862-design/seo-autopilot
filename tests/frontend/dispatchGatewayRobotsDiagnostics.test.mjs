import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const gateway = readFileSync(new URL("../../dispatch-gateway/main.py", import.meta.url), "utf8");

test("gateway exposes a release-sensitive robots policy diagnostic contract", () => {
  assert.match(gateway, /GATEWAY_CONTRACT_VERSION\s*=\s*"dispatch_gateway_robots_policy_diag_v1"/);
  assert.match(gateway, /"contract_version"\s*:\s*GATEWAY_CONTRACT_VERSION/);
  assert.match(gateway, /"source_sha"\s*:\s*GATEWAY_SOURCE_SHA/);
});

test("gateway distinguishes missing, non-boolean, and mismatched robots policy payloads", () => {
  for (const code of ["robots_policy_missing", "robots_policy_type", "robots_policy_pair"]) {
    assert.match(gateway, new RegExp(`"${code}"`));
  }
  assert.match(gateway, /"robots_policy_missing"\s*:\s*422/);
  assert.match(gateway, /"robots_policy_type"\s*:\s*400/);
  assert.match(gateway, /"robots_policy_pair"\s*:\s*412/);
  assert.match(gateway, /validation_status\s*=\s*ROBOTS_POLICY_STATUS\.get\(validation_error, 400\)/);
});
