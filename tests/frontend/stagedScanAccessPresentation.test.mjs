import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { buildCustomerProjection } from "../../base44/functions/getCustomerScanResultV9/projection.js";
import { durableScanStatePresentation } from "../../src/lib/durableScanStatePresentation.js";
import { resolveScanFunctionRoute } from "../../src/lib/scanFunctionRouting.js";
import { resolveScanOwnership } from "../../src/lib/siteOwnershipPolicy.js";

const respectRobots = { respect_robots_txt: true, owner_attested_robots_override: false, site_ownership_answer: "not_owner" };
const overrideRobots = { respect_robots_txt: false, owner_attested_robots_override: true, site_ownership_answer: "owner_or_manager" };

const failedRun = {
  id: "scan_test", project_id: "project_test", status: "failed", website_url: "https://example.com/",
  scan_mode: "standard_150", page_cap: 150, pipeline_mode: "staged", error_code: "scan_access_limited",
};

function projection(run, fullAccess = true) {
  return buildCustomerProjection({ run, fixItems: [], fullAccess, previewAccess: !fullAccess, authorityVerified: false });
}

function workerDetail(provider, reason) {
  return `${provider} returned ${reason} to the scanner, so FixList could not collect enough verified HTML debug_secret_123.`;
}

function asScript(file) {
  return readFileSync(file, "utf8").replace(/^import[\s\S]*?;\n/gm, "").replace(/^export\s+/gm, "");
}

function browserReader(result, generation) {
  const calls = [];
  const sdk = {
    auth: { me: async () => ({ id: "owner_test" }) },
    functions: { invoke: async (name, body) => { calls.push({ name, body }); return { data: result }; } },
  };
  const clientScript = asScript("src/api/base44Client.js").replace("import.meta.env?.VITE_SCAN_FUNCTION_GENERATION", "generation");
  const client = new Function("createClient", "appParams", "resolveScanFunctionRoute", "generation", `${clientScript}\nreturn base44;`)(
    () => sdk, {}, resolveScanFunctionRoute, generation,
  );
  const read = new Function("base44", "clearCustomerAuthBoundary", `${asScript("src/lib/scanRuns.js")}\nreturn getScanRunWithFixList;`)(client, () => {});
  return { calls, read };
}

test("the browser uses the V9 reader only when configured and preserves the exact failed run", async () => {
  const result = projection({ ...failedRun, ...respectRobots, status_detail: workerDetail("Cloudflare", "a bot challenge") });
  for (const [generation, name] of [[undefined, "getCustomerScanResultV8"], ["V9", "getCustomerScanResultV9"]]) {
    const response = generation === "V9" ? result : { ...result, run: { ...failedRun } };
    const { calls, read } = browserReader(response, generation);
    const bundle = await read(failedRun.id);
    assert.deepEqual(calls, [{ name, body: { scan_id: failedRun.id } }]);
    assert.equal(bundle.ok, true);
    assert.equal(bundle.authority_verified, false);
    assert.deepEqual(bundle.run.access_limitation, generation === "V9" ? { kind: "bot_challenge", provider: "cloudflare" } : undefined);
    assert.equal(Object.hasOwn(bundle.run, "status_detail"), false);
  }
});

test("known access restrictions get distinct, owner-aware advice at both page caps", () => {
  for (const [provider, reason, title, advice] of [
    ["Cloudflare", "a bot challenge", /Cloudflare.*challenge/i, /site administrator.*Cloudflare security events/i],
    ["SiteGround", "an automated-access block", /SiteGround.*blocked/i, /site administrator.*SiteGround security events/i],
    ["Cloudflare", "a rate limit", /Cloudflare.*rate.limit/i, /rate limit clears/i],
  ]) {
    for (const cap of [150, 500]) {
      const result = projection({ ...failedRun, ...overrideRobots, page_cap: cap, scan_mode: `standard_${cap}`,
        status_detail: workerDetail(provider, reason) }, false);
      assert.equal(result.access, "preview");
      assert.deepEqual(result.fixItems, []);
      const owner = durableScanStatePresentation(result.run, { ownership: resolveScanOwnership(result.run, "not_owner") });
      const visitor = durableScanStatePresentation(result.run, { ownership: "not_owner" });
      assert.equal(owner.kind, "security_service_blocked");
      assert.equal(visitor.kind, "access_limited");
      assert.match(owner.title, title);
      assert.match(visitor.nextStep, advice);
      assert.doesNotMatch(JSON.stringify([result, owner, visitor]), /always respects|debug_secret_123/i);
    }
  }
});

test("an exact robots denial respects the frozen policy and displays crawl-rule advice", () => {
  const denied = { ...failedRun, ...respectRobots, error_code: "blocked_by_robots_txt", status_detail: "private debug root" };
  const publicRun = projection(denied).run;
  assert.deepEqual(publicRun.access_limitation, { kind: "robots_blocked" });
  const view = durableScanStatePresentation(publicRun, { ownership: resolveScanOwnership(publicRun, "owner_or_manager") });
  assert.equal(view.kind, "robots_blocked");
  assert.match(view.nextStep, /section.*robots.txt allows/i);
  assert.doesNotMatch(JSON.stringify([publicRun, view]), /private debug|firewall/);
  const contradicted = projection({ ...denied, ...overrideRobots }).run;
  assert.equal(contradicted.access_limitation, undefined);
  assert.equal(Object.hasOwn(contradicted, "status_detail"), false);
  assert.notEqual(durableScanStatePresentation(contradicted).kind, "robots_blocked");
});

test("ordinary and unrecognized failures never promote an unsourced provider", () => {
  const unknown = projection({ ...failedRun, ...respectRobots, status_detail: workerDetail("Unrecognized", "a bot challenge") }).run;
  assert.deepEqual(unknown.access_limitation, { kind: "access_limited" });
  assert.doesNotMatch(JSON.stringify([unknown, durableScanStatePresentation(unknown)]), /Unrecognized|debug_secret_123/);
  const saveFailure = projection({ ...failedRun, ...respectRobots, error_code: "authority_write_failed",
    status_detail: workerDetail("Cloudflare", "a bot challenge") }).run;
  assert.equal(saveFailure.access_limitation, undefined);
  assert.equal(durableScanStatePresentation(saveFailure).kind, "save_failed");
});

test("a signed staged rate-limit reason shows wait advice without a provider guess", () => {
  const view = durableScanStatePresentation({ status: "limited", coverage_reasons: ["staged_rate_limit"],
    access_limitation: { kind: "bot_challenge", provider: "cloudflare" } });
  assert.match(view.title, /website.*rate.limit/i);
  assert.match(view.nextStep, /rate limit clears/i);
  assert.doesNotMatch(JSON.stringify(view), /Cloudflare/);
});
