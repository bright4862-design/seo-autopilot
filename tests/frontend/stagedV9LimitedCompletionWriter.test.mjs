import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";
import { buildLimitedResultSnapshot, verifyLimitedResultProof } from "../../base44/functions/getCustomerScanResultV9/limitedResultIntegrity.js";

const packageUrl = new URL("../../base44/functions/persistLimitedScanResultV9/", import.meta.url);
const modulePaths = [
  "./scanLimits.js", "./workerEnvelope.js", "./workerRuntime.js", "./generatedReleaseContract.js",
  "./generatedBuildId.js", "./completionTimestamp.js", "./limitedResultIntegrity.js",
];
const modules = Object.fromEntries(await Promise.all(modulePaths.map(async (path) => [
  path, await import(new URL(path, packageUrl)),
])));
const source = readFileSync(new URL("entry.ts", packageUrl), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const load = new Function("exports", "require", "Deno", "fetch", compiled);
const key = "limited-completion-test-key";
const startedAt = "2025-11-11T12:00:00.000Z";
const readyAt = "2025-11-11T12:03:47.521Z";
const identity = {
  scan_id: "scan_limited", project_id: "project_limited", owner_user_id: "owner_limited",
  request_id: "request_limited", attempt_count: 1, normalized_domain: "example.test",
};
const contract = { scan_mode: "standard_500", page_cap: 500, pipeline_mode: "staged" };
const robots = { respect_robots_txt: true, owner_attested_robots_override: false };

async function envelope(completedAt, scanFields = {}, reviewFields = {}) {
  const signed = {
    version: "durable_standard150_limited_v1",
    identity,
    scan: {
      ...contract, ...robots, submitted_url: "https://example.test/",
      pages_crawled: 50, pages_found: 500, worker_peak_memory_bytes: 100_000_000,
      scan_coverage: { urls_attempted: 50, usable_html_pages: 50, unique_retained_destinations: 50 },
      ...(completedAt ? { result_ready_at: completedAt } : {}),
      ...scanFields,
    },
    review: {
      coverage_state: "limited_coverage", scan_status: "limited",
      score_is_provisional: true, release_gate_eligible: false,
      coverage_authority_evidence: { coverage_authority_evidence_version: "fixture", assessment: "limited" },
      classification_integrity: {
        version: modules["./generatedReleaseContract.js"].RELEASE_COMPONENT_VERSIONS.acceptance_evidence_version,
        state: "limited_coverage", verdict: "limited_coverage", classifier_version: "fixture",
        evidence_sufficiency: "limited", usable_pages: 50, complete_small_site_inventory: false,
      },
      ...reviewFields,
    },
  };
  return {
    ...signed,
    proof: await modules["./workerEnvelope.js"].createAuthoritySeal(signed, key),
  };
}

function writerFixture(scanOverrides = {}, coordinator = null) {
  let run = {
    id: identity.scan_id, owner_user_id: identity.owner_user_id, project_id: identity.project_id,
    request_id: identity.request_id, attempt_count: 1, status: "reviewing", started_at: startedAt,
    ...contract, ...robots, ...scanOverrides,
  };
  let fixList;
  const fixItems = [];
  let writes = 0;
  const entities = {
    ScanRun: {
      get: async (id) => id === run.id ? structuredClone(run) : null,
      update: async (id, fields) => {
        assert.equal(id, run.id);
        writes++;
        run = { ...run, ...structuredClone(fields) };
      },
    },
    FixList: {
      filter: async () => fixList ? [structuredClone(fixList)] : [],
      get: async (id) => id === fixList?.id ? structuredClone(fixList) : null,
      create: async (fields) => {
        writes++;
        fixList = { ...structuredClone(fields), id: "list_limited" };
        return structuredClone(fixList);
      },
      update: async (id, fields) => {
        assert.equal(id, fixList.id);
        writes++;
        Object.assign(fixList, structuredClone(fields));
      },
    },
    FixItem: {
      filter: async () => structuredClone(fixItems),
      create: async fields => {
        writes++;
        fixItems.push({ ...structuredClone(fields), id: `item_${fixItems.length}` });
      },
    },
  };
  const dependencies = {
    ...modules,
    "npm:@base44/sdk@0.8.40": { createClientFromRequest: () => ({ asServiceRole: { entities } }) },
    "base44:runtime": { secrets: { get: (name) => {
      if (name === "SCAN_EVIDENCE_SIGNING_KEY") return key;
      assert.ok(coordinator);
      return { SCAN_ADMISSION_COORDINATOR_URL: "https://coordinator.example", BETA_SCAN_ADMISSION_ENABLED: "true" }[name];
    } } },
  };
  let handler;
  load({}, (name) => {
    assert.ok(Object.hasOwn(dependencies, name), `Unexpected dependency: ${name}`);
    return dependencies[name];
  }, { serve: (callback) => { handler = callback; } }, coordinator || (() => {
    assert.fail("The writer fixture must not make network requests");
  }));

  return {
    get writes() { return writes; },
    get run() { return structuredClone(run); },
    alterRun(fields) { Object.assign(run, fields); },
    alterList(fields) { Object.assign(fixList, fields); },
    alterItem(fields) { Object.assign(fixItems[0], fields); },
    async post(body) {
      const response = await handler(new Request("https://base44.example/functions/persistLimitedScanResultV9", {
        method: "POST",
        headers: { "X-FixList-Worker": "scan_job_worker_v1_cloud_tasks" },
        body: JSON.stringify(body),
      }));
      return { status: response.status, body: await response.json() };
    },
  };
}

test("V9 limited writer persists the signed ready time and replays the same proof", async () => {
  const fixture = writerFixture();
  const input = await envelope(readyAt);
  const tampered = await fixture.post({ ...input, scan: { ...input.scan, result_ready_at: startedAt } });
  assert.equal(tampered.status, 409);
  assert.equal(tampered.body.error_code, "worker_envelope_invalid");
  assert.equal(fixture.writes, 0);

  const first = await fixture.post(input);
  assert.equal(first.status, 200, JSON.stringify(first.body));
  assert.equal(first.body.resultIntegrityVerified, true);
  const run = first.body.scanRun;
  assert.equal(run.status, "limited");
  assert.equal(run.completed_at, readyAt);
  assert.equal(run.staged_writer_request_proof, input.proof);
  assert.equal(run.result_integrity_sealed_at, readyAt);
  const signedSnapshot = buildLimitedResultSnapshot({
    identity, scan: run, review: run, now: readyAt, version: run.result_integrity_version,
  });
  assert.equal(await verifyLimitedResultProof(signedSnapshot, key, run.result_integrity_proof), true);
  assert.equal(await verifyLimitedResultProof({ ...signedSnapshot, sealed_at: startedAt }, key, run.result_integrity_proof), false);

  const writes = fixture.writes;
  const replay = await fixture.post(input);
  assert.equal(replay.status, 200, JSON.stringify(replay.body));
  assert.equal(replay.body.replayed, true);
  assert.equal(replay.body.fixListId, first.body.fixListId);
  assert.equal(replay.body.scanRun.result_integrity_proof, run.result_integrity_proof);
  assert.equal(replay.body.scanRun.completed_at, readyAt);
  assert.equal(fixture.writes, writes);
  const newRequest = await envelope(readyAt, { synthetic_request_marker: true });
  const conflict = await fixture.post(newRequest);
  assert.equal(conflict.status, 409);
  assert.equal(conflict.body.error_code, "limited_result_immutable");
  assert.equal(fixture.writes, writes);
});

test("a valid but different signed limited completion cannot overwrite its settled report", async () => {
  const fixture = writerFixture();
  const original = await envelope(readyAt);
  const first = await fixture.post(original);
  assert.equal(first.status, 200);
  const writes = fixture.writes;
  const different = await envelope(readyAt, { pages_found: 501 });
  const response = await fixture.post(different);
  assert.equal(response.status, 409);
  assert.equal(response.body.error_code, "limited_result_immutable");
  assert.deepEqual(fixture.run, first.body.scanRun);
  assert.equal(fixture.writes, writes);
});

test("terminal limited replay checks the saved list and item content before acknowledging", async () => {
  for (const damage of [
    fixture => fixture.alterList({ owner_user_id: "another_owner" }),
    fixture => fixture.alterList({ health_score: 100 }),
    fixture => fixture.alterItem({ issue_title: "changed" }),
  ]) {
    const document = await envelope(readyAt, {}, {
      recommendations: [{ fix_id: "fixture_fix", issue_title: "Fix a page title" }],
    });
    const fixture = writerFixture();
    assert.equal((await fixture.post(document)).status, 200);
    const writes = fixture.writes;
    assert.equal((await fixture.post(document)).body.replayed, true);
    damage(fixture);
    const response = await fixture.post(document);
    assert.equal(response.status, 409);
    assert.equal(response.body.error_code, "limited_result_invalid");
    assert.equal(fixture.writes, writes);
  }
});

test("a terminal limited replay must still belong to the stored account, project, request and attempt", async () => {
  const input = await envelope(readyAt);
  for (const overrides of [
    { owner_user_id: "other_owner" }, { project_id: "other_project" }, { request_id: "other_request" },
    { attempt_count: 2 }, { status: "cancelled" }, { status: "failed" },
  ]) {
    const fixture = writerFixture();
    assert.equal((await fixture.post(input)).status, 200);
    fixture.alterRun(overrides);
    const writes = fixture.writes;
    const result = await fixture.post(input);
    assert.equal(result.status, 409);
    assert.equal(fixture.writes, writes);
  }
});

test("both the initial limited save and terminal replay wait for confirmed admission release", async () => {
  let coordinatorAvailable = false;
  let releaseCalls = 0;
  const fixture = writerFixture({
    admission_access_id: "fixture_access", admission_release_state: "pending",
    admission_barrier_generation: 3, admission_claim_sequence: 4, idempotency_key: identity.request_id,
  }, async (url) => {
    assert.equal(url, "https://coordinator.example/release");
    releaseCalls++;
    return coordinatorAvailable
      ? Response.json({ success: true, outcome: "released", scan_id: identity.scan_id,
        request_id: identity.request_id, barrier_generation: 3, claim_sequence: 4 })
      : Response.json({}, { status: 503 });
  });
  const input = await envelope(readyAt);
  for (let i = 0; i < 2; i++) {
    const response = await fixture.post(input);
    assert.equal(response.status, 503);
    assert.equal(response.body.error_code, "admission_release_pending");
    assert.equal(fixture.run.status, "limited");
    assert.equal(fixture.run.admission_release_state, "pending");
  }
  coordinatorAvailable = true;
  const replay = await fixture.post(input);
  assert.equal(replay.body.replayed, true);
  assert.equal(replay.body.scanRun.admission_release_state, "released");
  const writes = fixture.writes;
  assert.equal((await fixture.post(input)).body.replayed, true);
  assert.equal(releaseCalls, 3);
  assert.equal(fixture.writes, writes);
});

test("historical V9 limited replay preserves the earlier seal and completion time", async () => {
  const previousCompletion = "2025-11-11T12:02:31.100Z";
  const fixture = writerFixture({ completed_at: previousCompletion });
  const first = await fixture.post(await envelope());
  assert.equal(first.status, 200, JSON.stringify(first.body));
  assert.equal(first.body.scanRun.result_integrity_sealed_at, startedAt);
  assert.equal(first.body.scanRun.completed_at, previousCompletion);

  fixture.alterRun({ staged_writer_request_proof: null });
  const writes = fixture.writes;
  const replay = await fixture.post(await envelope(readyAt));
  assert.equal(replay.status, 200, JSON.stringify(replay.body));
  assert.equal(replay.body.replayed, true);
  assert.equal(replay.body.scanRun.result_integrity_proof, first.body.scanRun.result_integrity_proof);
  assert.equal(replay.body.scanRun.result_integrity_sealed_at, startedAt);
  assert.equal(replay.body.scanRun.completed_at, previousCompletion);
  assert.equal(fixture.writes, writes);
});

test("V9 limited persistence seals the unconfirmed target cooldown with the saved report", async () => {
  const publication = {
    state: "unconfirmed",
    reason: "publication_unavailable",
    observation: {
      status_code: 429,
      target_origin: "https://example.test:443",
      observed_at: Date.parse(startedAt) / 1000,
      retry_after_seconds: 3600,
    },
  };
  const fixture = writerFixture();
  const input = await envelope(readyAt, { crawl_timing: { target_cooldown_publication: publication } });
  const first = await fixture.post(input);
  assert.equal(first.status, 200, JSON.stringify(first.body));
  const run = first.body.scanRun;
  assert.equal(run.status, "limited");
  assert.deepEqual(run.crawl_timing?.target_cooldown_publication, publication);

  const args = { identity, scan: run, review: run, now: readyAt, version: run.result_integrity_version };
  const snapshot = buildLimitedResultSnapshot(args);
  assert.equal(await verifyLimitedResultProof(snapshot, key, run.result_integrity_proof), true);
  const tamperedRun = { ...run, crawl_timing: { target_cooldown_publication: { ...publication, state: "acknowledged" } } };
  const tamperedSnapshot = buildLimitedResultSnapshot({ ...args, scan: tamperedRun });
  assert.equal(await verifyLimitedResultProof(tamperedSnapshot, key, run.result_integrity_proof), false);

  const replay = await fixture.post(input);
  assert.equal(replay.body.replayed, true);
  assert.equal(replay.body.scanRun.result_integrity_proof, run.result_integrity_proof);
});
