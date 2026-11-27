import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { buildCustomerProjection } from "../../base44/functions/getCustomerScanResultV9/projection.js";
import { durableScanStatePresentation } from "../../src/lib/durableScanStatePresentation.js";
import { parsePublishedScanOptions, resolveScanFunctionRoute } from "../../src/lib/scanFunctionRouting.js";
import { resolveScanOwnership } from "../../src/lib/siteOwnershipPolicy.js";
import publicRouteContract from "../../data/base44-function-routes.json" with { type: "json" };
import deployments from "../../data/generated-staged-v9-routes.json" with { type: "json" };

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
  return { calls, read, invoke: client.functions.invoke };
}

test("the browser uses the configured reader first and preserves the exact failed run", async () => {
  const result = projection({ ...failedRun, ...respectRobots, status_detail: workerDetail("Cloudflare", "a bot challenge") });
  for (const [generation, name] of [[undefined, "getCustomerScanResultV8"], ["V9", deployments.functions.getCustomerScanResultV9.route_name]]) {
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

test("the public manifest selects start, result, and deletion routes together", () => {
  const v9 = {
    generation: "v9",
    routes: publicRouteContract.candidate_routes.v9,
    historical_routes: {v8: publicRouteContract.routes},
  };
  for (const name of ["startStandardScanJob", "getCustomerScanResult", "deleteCustomerScanData"]) {
    const entry = `${name}V8`;
    assert.equal(resolveScanFunctionRoute(entry), entry);
    assert.equal(resolveScanFunctionRoute(entry, undefined, v9), deployments.functions[`${name}V9`].route_name);
    assert.equal(resolveScanFunctionRoute(entry, "V8", v9), deployments.functions[`${name}V9`].route_name);
  }
  assert.equal(resolveScanFunctionRoute("createAccessCheckout", undefined, v9), "createAccessCheckout");
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

test("published pilot leaves the legacy launcher available and selects only its pinned readers", () => {
  assert.equal(resolveScanFunctionRoute("startStandardScanJobV8", "PUBLISHED_PILOT"), "startStandardScanJobV8");
  for (const name of ["getCustomerScanResult", "deleteCustomerScanData"]) {
    assert.equal(resolveScanFunctionRoute(name + "V8", "PUBLISHED_PILOT"), deployments.functions[name + "V9"].route_name);
  }
});

test("published launch options accept only a known release and one allowed cap", () => {
  const fingerprint = "a".repeat(16);
  const response = { success: true, version: "published_scan_options_v1", release_fingerprint: fingerprint };
  for (const page_cap of [150, 500]) {
    const result = parsePublishedScanOptions({ ...response, launch: "pilot", page_cap }, fingerprint);
    assert.deepEqual(result, { pilot: true, pageCap: page_cap });
  }
  assert.deepEqual(parsePublishedScanOptions({ ...response, launch: "legacy", page_cap: 150 }, fingerprint),
    { pilot: false, pageCap: 150 });
  for (const invalid of [
    { ...response, launch: "pilot", page_cap: 501 },
    { ...response, launch: "legacy", page_cap: 500 },
    { ...response, launch: "pilot", page_cap: 500, release_fingerprint: "b".repeat(16) },
    { ...response, launch: "paused", page_cap: null },
  ]) {
    assert.throws(() => parsePublishedScanOptions(invalid, fingerprint), /could not be verified|paused/);
  }
});

test("published pilot falls back for a historical read or an unavailable route, but honors a scan refusal", async () => {
  const source = asScript("src/api/base44Client.js").replace("import.meta.env?.VITE_SCAN_FUNCTION_GENERATION", "generation");
  const v9 = deployments.functions.getCustomerScanResultV9.route_name;
  const calls = [];
  const sdk = { functions: { invoke: async (name, body) => {
    calls.push({ name, body });
    if (name !== v9) return { data: { success: true } };
    const error = new Error("read failed");
    error.response = { status: body.status ?? 503, data: { error_code: body.scenario } };
    throw error;
  } } };
  const client = new Function("createClient", "appParams", "resolveScanFunctionRoute", "generation", source + "\nreturn base44;")(
    () => sdk, {}, resolveScanFunctionRoute, "PUBLISHED_PILOT",
  );
  const historical = { scan_id: "history_001", scenario: "result_release_mismatch" };
  assert.deepEqual(await client.functions.invoke("getCustomerScanResultV8", historical), { data: { success: true } });
  assert.deepEqual(calls.map(call => call.name), [v9, "getCustomerScanResultV8"]);
  calls.length = 0;
  const lostRoute = { scan_id: historical.scan_id, status: 404 };
  await client.functions.invoke("getCustomerScanResultV8", lostRoute);
  assert.deepEqual(calls.map(call => call.name), [v9, "getCustomerScanResultV8"]);
  calls.length = 0;
  await assert.rejects(client.functions.invoke("getCustomerScanResultV8", { ...lostRoute, scenario: "scan_not_found" }));
  assert.deepEqual(calls.splice(0).map(call => call.name), [v9]);
  await assert.rejects(client.functions.invoke("getCustomerScanResultV8", { ...historical, status: 401 }));
  assert.deepEqual(calls.map(call => call.name), [v9]);
});

test("a default V8 build retries only a release-mismatched saved report through the exact V9 reader", async () => {
  const source = asScript("src/api/base44Client.js").replace("import.meta.env?.VITE_SCAN_FUNCTION_GENERATION", "generation");
  const v8 = "getCustomerScanResultV8";
  const v9 = deployments.functions.getCustomerScanResultV9.route_name;
  const scanId = "archived_001";
  const calls = [];
  let failure = { status: 503, data: { error_code: "result_release_mismatch" } };
  let returnedId = scanId;
  const sdk = {
    auth: { me: async () => ({ id: "owner_test" }) },
    functions: { invoke: async (name, body) => {
      calls.push({ name, body });
      if (name === v9) return { data: {
        success: true, scan_id: returnedId, access: "full", authority_verified: true,
        run: { id: returnedId, project_id: "project_test", status: "complete", beta_revision_fingerprint: "b36ca24b8e0f728e" },
        fixItems: [],
      } };
      throw Object.assign(new Error("reader failed"), { response: failure });
    } },
  };
  const client = new Function("createClient", "appParams", "resolveScanFunctionRoute", "generation", source + "\nreturn base44;")(
    () => sdk, {}, resolveScanFunctionRoute, undefined,
  );
  const read = new Function("base44", "clearCustomerAuthBoundary", `${asScript("src/lib/scanRuns.js")}
return getScanRunWithFixList;`)(client, () => {});
  const result = await read(scanId);
  assert.equal(result.ok, true);
  assert.equal(result.authority_verified, true);
  assert.equal(result.run.beta_revision_fingerprint, "b36ca24b8e0f728e");
  assert.deepEqual(calls.splice(0), [v8, v9].map(name => ({ name, body: { scan_id: scanId } })));

  returnedId = "wrong_scan";
  assert.equal((await read(scanId)).kind, "authority_invalid");
  calls.length = 0;
  for (const [name, body] of [
    ["startStandardScanJobV8", { scan_id: scanId, published_pilot_page_cap: 500 }],
    ["deleteCustomerScanDataV8", { scan_id: scanId }],
    [v8, { action: "list", scan_id: scanId }],
    [v8, { action: "compare", scan_id: scanId }],
    [v8, { scan_id: scanId, scan_run_id: "wrong_scan" }],
    [v8, { scan_id: scanId, data: { scan_id: "wrong_scan" } }],
    [v8, { scan_id: "" }],
  ]) {
    await assert.rejects(client.functions.invoke(name, body));
    assert.deepEqual(calls.splice(0), [{ name, body }]);
  }

  for (const [status, error_code] of [
    [401, "unauthorized"], [403, "result_release_mismatch"], [403, "forbidden"],
    [503, "result_authority_invalid"], [404, "scan_not_found"], [503, undefined],
  ]) {
    failure = { status, data: { error_code } };
    await assert.rejects(client.functions.invoke(v8, { scan_id: scanId }));
    assert.deepEqual(calls.splice(0), [{ name: v8, body: { scan_id: scanId } }]);
  }
});

test("an unavailable pilot capability leaves Standard 150 available, but a known pilot pause stays in effect", async () => {
  const source = asScript("src/api/base44Client.js").replace("import.meta.env?.VITE_SCAN_FUNCTION_GENERATION", "generation");
  const fingerprint = "a".repeat(16);
  let nextResponse = Object.assign(new Error("temporarily missing"), { status: 404 });
  const calls = [];
  const sdk = { functions: { invoke: async (name, body) => {
    calls.push({ name, body });
    if (nextResponse instanceof Error) throw nextResponse;
    return { data: nextResponse };
  } } };
  const options = new Function("createClient", "appParams", "resolveScanFunctionRoute", "generation",
    "parsePublishedScanOptions", "RELEASE_FINGERPRINT", source + "\nreturn readPublishedScanOptions;")(
    () => sdk, {}, resolveScanFunctionRoute, "PUBLISHED_PILOT", parsePublishedScanOptions, fingerprint,
  );
  assert.deepEqual(await options(), { pageCap: 150, pilot: false, pilotUnavailable: true });
  const paused = { success: true, version: "published_scan_options_v1", release_fingerprint: fingerprint,
    launch: "paused", page_cap: null };
  nextResponse = paused;
  await assert.rejects(options(), /pilot scans are paused/);
  nextResponse = Object.assign(new Error("unauthorized"), { status: 401 });
  await assert.rejects(options(), /unauthorized/);
  const launcher = deployments.functions.startStandardScanJobV9.route_name;
  assert.deepEqual(calls, Array.from({ length: 3 }, () => ({ name: launcher, body: { action: "published_scan_options" } })));
});

test("the normal form launch chooses V9 only after it has a server-confirmed pilot cap", async () => {
  const { calls, invoke } = browserReader({ success: true }, "PUBLISHED_PILOT");
  const payload = { request_id: "same_identity_for_all_retries", scan_mode: "standard_150" };
  await invoke("startStandardScanJobV8", payload);
  await invoke("startStandardScanJobV8", { ...payload, published_pilot_page_cap: 500 });
  assert.deepEqual(calls, [
    { name: "startStandardScanJobV8", body: payload },
    { name: deployments.functions.startStandardScanJobV9.route_name, body: { ...payload, published_pilot_page_cap: 500 } },
  ]);
});


test("PAID_PILOT requires public V9 and never downgrades ordinary 150 launches to V8", async () => {
  const routes = { generation: "v9", routes: publicRouteContract.candidate_routes.v9 };
  assert.throws(() => resolveScanFunctionRoute("startStandardScanJobV8", "PAID_PILOT"), /staged scanner route is unavailable/);
  const calls = [];
  const sdk = { functions: { invoke: async (name, body) => { calls.push({ name, body }); return { data: { success: true } }; } } };
  const source = asScript("src/api/base44Client.js").replace("import.meta.env?.VITE_SCAN_FUNCTION_GENERATION", "generation");
  const client = new Function("createClient", "appParams", "resolveScanFunctionRoute", "generation", source + "\nreturn {base44, usesPublishedScanPilot};")(
    () => sdk, {}, (name, generation) => resolveScanFunctionRoute(name, generation, routes), "PAID_PILOT",
  );
  assert.equal(client.usesPublishedScanPilot, true);
  for (const payload of [{ request_id: "public_150" }, { request_id: "named_500", published_pilot_page_cap: 500 }]) {
    await client.base44.functions.invoke("startStandardScanJobV8", payload);
  }
  assert.deepEqual(calls.map(row => row.name), Array(2).fill(deployments.functions.startStandardScanJobV9.route_name));
  for (const name of ["getCustomerScanResult", "deleteCustomerScanData"]) {
    assert.equal(resolveScanFunctionRoute(name + "V8", "PAID_PILOT", routes), deployments.functions[name + "V9"].route_name);
  }
});

test("PAID_PILOT reads verified options from the active V9 launcher and fails closed when it is unavailable", async () => {
  const routes = { generation: "v9", routes: publicRouteContract.candidate_routes.v9 };
  const fingerprint = "a".repeat(16);
  const calls = [];
  let response = { success: true, version: "published_scan_options_v1", release_fingerprint: fingerprint, launch: "legacy", page_cap: 150 };
  const sdk = { functions: { invoke: async (name, body) => {
    calls.push({ name, body });
    if (response instanceof Error) throw response;
    return { data: response };
  } } };
  const source = asScript("src/api/base44Client.js").replace("import.meta.env?.VITE_SCAN_FUNCTION_GENERATION", "generation");
  const options = new Function("createClient", "appParams", "resolveScanFunctionRoute", "generation",
    "parsePublishedScanOptions", "RELEASE_FINGERPRINT", source + "\nreturn readPublishedScanOptions;")(
    () => sdk, {}, (name, generation) => resolveScanFunctionRoute(name, generation, routes), "PAID_PILOT", parsePublishedScanOptions, fingerprint,
  );
  assert.deepEqual(await options(), { pageCap: 150, pilot: false });
  response = { ...response, launch: "pilot", page_cap: 500 };
  assert.deepEqual(await options(), { pageCap: 500, pilot: true });
  response = Object.assign(new Error("temporarily missing"), { status: 404 });
  await assert.rejects(options(), /temporarily missing/);
  assert.deepEqual(calls, Array.from({ length: 3 }, () => ({
    name: deployments.functions.startStandardScanJobV9.route_name, body: { action: "published_scan_options" },
  })));
});
