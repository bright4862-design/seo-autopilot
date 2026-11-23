import assert from "node:assert/strict";
import { createServer } from "node:http";
import { spawn, spawnSync } from "node:child_process";
import { chmodSync, cpSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  approvedComparisonEvidenceProperty,
  assessInventory,
  comparisonEvidenceIsEmpty,
  diffEntity,
  functionInventoryProblems,
  hmacContractProblems,
  liveDiffIsOnlyComparisonEvidence,
  mutateLiveScanRun,
  readLocalSchema,
  signingContinuity,
  signingSecretPresence,
} from "../../scripts/base44_authority_schema.mjs";

const workflow = readFileSync(".github/workflows/fixlist-cloud-operator.yml", "utf8");
const migration = readFileSync("scripts/migrate-scanrun-comparison-evidence.sh", "utf8");
const preflight = readFileSync("scripts/base44-v8-preflight.sh", "utf8");
const clientSource = readFileSync("scripts/base44_named_schema_client.mjs", "utf8");

function localInventory(mutateScan = (schema) => schema) {
  const scan = structuredClone(readLocalSchema("ScanRun"));
  return {
    ScanRun: mutateScan(scan),
    FixList: readLocalSchema("FixList"),
    FixItem: readLocalSchema("FixItem"),
  };
}

test("ScanRun.comparison_evidence matches the sealed object the worker and readers use", () => {
  const schema = readLocalSchema("ScanRun");
  const field = schema.properties.comparison_evidence;
  assert.equal(field.type, "object");
  assert.equal(field.additionalProperties, true);
  assert.deepEqual(field.default, {});
  assert.equal(field.rls.write.user_condition.role, "admin");
  assert.equal(schema.required.includes("comparison_evidence"), false);
  assert.match(field.description, /rescan comparisons/);
});

test("schema parity allows only the additive comparison_evidence gap", () => {
  const missing = localInventory((schema) => {
    delete schema.properties.comparison_evidence;
    return schema;
  });
  const additive = assessInventory(missing);
  assert.equal(additive.decision, "apply");
  assert.equal(additive.reports.find((report) => report.entity === "ScanRun").status, "additive_comparison_evidence");

  const matched = assessInventory(localInventory());
  assert.equal(matched.decision, "match");

  const drifted = localInventory((schema) => {
    delete schema.properties.comparison_evidence;
    delete schema.properties.pages_crawled;
    return schema;
  });
  assert.equal(assessInventory(drifted).decision, "refuse");

  const otherEntity = localInventory((schema) => {
    delete schema.properties.comparison_evidence;
    return schema;
  });
  delete otherEntity.FixList.properties.website_url;
  assert.equal(assessInventory(otherEntity).decision, "refuse");

  const changed = localInventory((schema) => {
    schema.properties.comparison_evidence.rls = { write: { user_condition: { role: "user" } } };
    return schema;
  });
  assert.equal(diffEntity("ScanRun", readLocalSchema("ScanRun"), changed.ScanRun).status, "drift");
});

test("live schema mutation changes only comparison_evidence", () => {
  const live = readLocalSchema("ScanRun");
  delete live.properties.comparison_evidence;
  delete live.properties.website_url.description;
  live.properties.created_date = { type: "string" };
  live.platform_marker = "live-only";
  const approved = approvedComparisonEvidenceProperty();
  const applied = mutateLiveScanRun(live, "apply", approved);
  assert.equal(applied.platform_marker, "live-only");
  assert.deepEqual(applied.properties.created_date, { type: "string" });
  assert.equal(Object.hasOwn(applied.properties.website_url, "description"), false);
  assert.deepEqual(applied.properties.comparison_evidence, approved);
  assert.equal(liveDiffIsOnlyComparisonEvidence(live, applied, "apply", approved), true);
  const rolled = mutateLiveScanRun(applied, "rollback", approved);
  assert.equal(Object.hasOwn(rolled.properties, "comparison_evidence"), false);
  assert.equal(rolled.platform_marker, "live-only");
  assert.equal(liveDiffIsOnlyComparisonEvidence(applied, rolled, "rollback", approved), true);
  const tampered = structuredClone(applied);
  tampered.properties.website_url.description = "rewritten";
  assert.equal(liveDiffIsOnlyComparisonEvidence(live, tampered, "apply", approved), false);
  const echoed = structuredClone(applied);
  delete echoed.properties.comparison_evidence.description;
  delete echoed.properties.comparison_evidence.default;
  delete echoed.properties.comparison_evidence.additionalProperties;
  assert.equal(liveDiffIsOnlyComparisonEvidence(live, echoed, "apply", approved), true);
});

test("stored comparison evidence is empty only for missing or blank values", () => {
  assert.equal(comparisonEvidenceIsEmpty(undefined), true);
  assert.equal(comparisonEvidenceIsEmpty(null), true);
  assert.equal(comparisonEvidenceIsEmpty({}), true);
  assert.equal(comparisonEvidenceIsEmpty(""), true);
  assert.equal(comparisonEvidenceIsEmpty({ version: "scan_comparison_evidence_v1_missing_h1" }), false);
  assert.equal(comparisonEvidenceIsEmpty(0), false);
});

test("signing continuity compares pinned references and never accepts plaintext", () => {
  const service = (version) => ({
    spec: { template: { spec: { containers: [{ env: [
      { name: "SCAN_EVIDENCE_SIGNING_KEY", valueFrom: { secretKeyRef: { name: "SCAN_EVIDENCE_SIGNING_KEY", key: version } } },
    ] }] } } },
  });
  const match = signingContinuity({
    worker: service("4"),
    gateway: service("4"),
    coordinator: service("4"),
  });
  assert.equal(match.ok, true);
  const mismatch = signingContinuity({
    worker: service("4"),
    gateway: service("5"),
    coordinator: service("4"),
  });
  assert.equal(mismatch.ok, false);
  const plaintext = signingContinuity({
    worker: { spec: { template: { spec: { containers: [{ env: [{ name: "SCAN_EVIDENCE_SIGNING_KEY", value: "secret" }] }] } } } },
    gateway: service("4"),
    coordinator: service("4"),
  });
  assert.equal(plaintext.refs.worker.error, "plaintext");
  assert.equal(signingSecretPresence("SCAN_EVIDENCE_SIGNING_KEY\nOTHER\n").present, true);
  assert.equal(signingSecretPresence("SCAN_EVIDENCE_SIGNING_KEY=hidden\n").present, false);
});

test("function inventory and source HMAC contract cover the V8 release", () => {
  const listed = ["  startStandardScanJobV8", "durableScanWorkerControlV8", "persistDurableScanAuthorityV8", "persistLimitedScanResultV8", "getCustomerScanResultV8", "deleteCustomerScanDataV8"].join("\n");
  assert.deepEqual(functionInventoryProblems(listed), []);
  assert.equal(functionInventoryProblems("startStandardScanJobV8\n").length, 5);
  assert.deepEqual(hmacContractProblems(), []);
});

test("Base44 inventory entries must be standalone lines, not mentions in CLI diagnostics", () => {
  const names = [
    "startStandardScanJobV8",
    "durableScanWorkerControlV8",
    "persistDurableScanAuthorityV8",
    "persistLimitedScanResultV8",
    "getCustomerScanResultV8",
    "deleteCustomerScanDataV8",
  ];
  assert.deepEqual(functionInventoryProblems(names.map((name) => `  ${name}`).join("\n")), []);
  assert.equal(functionInventoryProblems(`Warning: ${names.join(", ")}`).length, 6);
  assert.equal(functionInventoryProblems(names.map((name) => `not deployed: ${name}`).join("\n")).length, 6);
  assert.deepEqual(
    functionInventoryProblems(`  \u001b[32m${names[0]}\u001b[0m\n${names.slice(1).join("\n")}`),
    [],
  );
  assert.equal(signingSecretPresence("Warning: SCAN_EVIDENCE_SIGNING_KEY is missing").present, false);
  assert.equal(signingSecretPresence("  \u001b[32mSCAN_EVIDENCE_SIGNING_KEY\u001b[0m  \n").present, true);
  assert.equal(signingSecretPresence("SCAN_EVIDENCE_SIGNING_KEY=hidden\n").present, false);
});

function run(command, args, options) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, options);
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("error", reject);
    child.on("close", (status) => resolve({ status, stdout, stderr }));
  });
}

test("named schema client updates only ScanRun and refuses bulk sync", async () => {
  assert.match(clientSource, /bulk entity sync payload is prohibited/);
  assert.doesNotMatch(clientSource, /entityNameToSchema\s*:/);
  assert.match(clientSource, /\/entity-schemas\/\$\{ENTITY_NAME\}/);
  const seen = [];
  const server = createServer((request, response) => {
    seen.push(`${request.method} ${request.url}`);
    const chunks = [];
    request.on("data", (chunk) => chunks.push(chunk));
    request.on("end", () => {
      if (request.method === "PUT") {
        const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
        assert.equal(body.entity_schema.name, "ScanRun");
        assert.equal(Object.hasOwn(body, "entityNameToSchema"), false);
      }
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({
        schemas: [
          { entity_name: "ScanRun", entity_schema: readLocalSchema("ScanRun") },
          { entity_name: "FixList", entity_schema: readLocalSchema("FixList") },
          { entity_name: "FixItem", entity_schema: readLocalSchema("FixItem") },
        ],
      }));
    });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  const root = mkdtempSync(join(tmpdir(), "schema-client-"));
  const auth = join(root, "auth.json");
  writeFileSync(auth, JSON.stringify({ accessToken: "x".repeat(40) }));
  const inventory = join(root, "inventory.json");
  const schema = join(root, "scanrun.json");
  writeFileSync(schema, JSON.stringify(readLocalSchema("ScanRun")));
  const env = {
    ...process.env,
    BASE44_SCHEMA_API_FIXTURE: `http://127.0.0.1:${address.port}`,
    BASE44_AUTH_FILE: auth,
    BASE44_API_KEY: "",
    GITHUB_ACTIONS: "",
  };
  try {
    const fetched = await run("node", ["scripts/base44_named_schema_client.mjs", "fetch", inventory], { env });
    assert.equal(fetched.status, 0, fetched.stderr);
    const put = await run("node", ["scripts/base44_named_schema_client.mjs", "put", schema], { env });
    assert.equal(put.status, 0, put.stderr);
    assert.deepEqual(seen, [
      "GET /api/apps/6a498732ec779dfaaeab0e53/entity-schemas",
      "PUT /api/apps/6a498732ec779dfaaeab0e53/entity-schemas/ScanRun",
    ]);
  } finally {
    server.close();
    rmSync(root, { recursive: true, force: true });
  }
});

function migrationFixture({ operatorExit = 0 } = {}) {
  const root = mkdtempSync(join(tmpdir(), "schema-migration-"));
  mkdirSync(join(root, "scripts", "lib"), { recursive: true });
  mkdirSync(join(root, "base44", "entities"), { recursive: true });
  cpSync("scripts/migrate-scanrun-comparison-evidence.sh", join(root, "scripts/migrate-scanrun-comparison-evidence.sh"));
  cpSync("scripts/base44_authority_schema.mjs", join(root, "scripts/base44_authority_schema.mjs"));
  cpSync("scripts/base44_named_schema_client.mjs", join(root, "scripts/base44_named_schema_client.mjs"));
  for (const name of ["ScanRun", "FixList", "FixItem"]) {
    cpSync(`base44/entities/${name}.jsonc`, join(root, "base44/entities", `${name}.jsonc`));
  }
  writeFileSync(join(root, "scripts/lib/release-source-guard.sh"), `
fixlist_require_exact_main() { FIXLIST_EXACT_SOURCE_SHA="$2"; export FIXLIST_EXACT_SOURCE_SHA; printf 'source_sha=%s\\n' "$2"; }
`);
  writeFileSync(join(root, "scripts/lib/base44-pinned-cli.sh"), `
fixlist_install_base44_cli() { FIXLIST_BASE44_CLI=true; export FIXLIST_BASE44_CLI; }
fixlist_require_base44_owner() { :; }
`);
  const operatorLog = join(root, "operator.log");
  writeFileSync(join(root, "scripts/fixlist-cloud-operator.sh"), `#!/usr/bin/env bash
printf 'operation=%s confirm=%s mode=%s\\n' "$OPERATION" "$CONFIRM" "$BARRIER_EXPECTED_PRIOR_MODE" >> "$TEST_OPERATOR_LOG"
exit ${operatorExit}
`);
  chmodSync(join(root, "scripts/fixlist-cloud-operator.sh"), 0o755);
  return { root, operatorLog };
}

test("schema migration is refused before the barrier or Base44 when confirmation is wrong", () => {
  const fixture = migrationFixture();
  const sha = "a".repeat(40);
  try {
    const result = spawnSync("bash", ["scripts/migrate-scanrun-comparison-evidence.sh"], {
      cwd: fixture.root,
      encoding: "utf8",
      env: {
        ...process.env,
        ACTION: "apply",
        SOURCE_SHA: sha,
        CONFIRM: `APPLY-SCANRUN-COMPARISON-EVIDENCE:${sha}:76`,
        BARRIER_EXPECTED_GENERATION: "77",
        BARRIER_EXPECTED_PRIOR_MODE: "closed",
        TEST_OPERATOR_LOG: fixture.operatorLog,
      },
    });
    assert.equal(result.status, 2, result.stderr);
    assert.throws(() => readFileSync(fixture.operatorLog, "utf8"));
  } finally {
    rmSync(fixture.root, { recursive: true, force: true });
  }
});

test("schema migration proves the closed barrier before the named ScanRun update", async () => {
  const fixture = migrationFixture();
  const sha = "b".repeat(40);
  const schemas = localInventory((schema) => {
    delete schema.properties.comparison_evidence;
    delete schema.properties.website_url.description;
    schema.properties.created_date = { type: "string" };
    schema.platform_marker = "live-only";
    return schema;
  });
  let stored = structuredClone(schemas.ScanRun);
  const puts = [];
  const server = createServer((request, response) => {
    const chunks = [];
    request.on("data", (chunk) => chunks.push(chunk));
    request.on("end", () => {
      if (request.method === "PUT") {
        const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
        puts.push(body.entity_schema);
        stored = body.entity_schema;
      }
      const inventory = { ...schemas, ScanRun: stored };
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({
        schemas: Object.entries(inventory).map(([entity_name, entity_schema]) => ({ entity_name, entity_schema })),
      }));
    });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  const auth = join(fixture.root, "auth.json");
  writeFileSync(auth, JSON.stringify({ accessToken: "y".repeat(40) }));
  try {
    const result = await run("bash", ["scripts/migrate-scanrun-comparison-evidence.sh"], {
      cwd: fixture.root,
      env: {
        ...process.env,
        ACTION: "apply",
        SOURCE_SHA: sha,
        CONFIRM: `APPLY-SCANRUN-COMPARISON-EVIDENCE:${sha}:77`,
        BARRIER_EXPECTED_GENERATION: "77",
        BARRIER_EXPECTED_PRIOR_MODE: "closed",
        CHANGE_TICKET: "incident-378",
        BASE44_EXPECTED_OWNER: "owner@example.com",
        BASE44_SCHEMA_API_FIXTURE: `http://127.0.0.1:${address.port}`,
        BASE44_AUTH_FILE: auth,
        BASE44_API_KEY: "",
        GITHUB_ACTIONS: "",
        TEST_OPERATOR_LOG: fixture.operatorLog,
        GCP_ADMISSION_OPERATOR_SERVICE_ACCOUNT: "fixlist-admission-operator@example.iam.gserviceaccount.com",
      },
    });
    assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
    const operator = readFileSync(fixture.operatorLog, "utf8");
    assert.match(operator, /operation=verify-zero-admission-obligations/);
    assert.match(operator, new RegExp(`confirm=VERIFY-ZERO-ADMISSION:${sha}:77`));
    assert.match(operator, /mode=closed/);
    assert.equal(puts.length, 1);
    assert.equal(puts[0].platform_marker, "live-only");
    assert.deepEqual(puts[0].properties.created_date, { type: "string" });
    assert.equal(Object.hasOwn(puts[0].properties.website_url, "description"), false);
    assert.deepEqual(puts[0].properties.comparison_evidence, approvedComparisonEvidenceProperty());
    assert.match(result.stdout, /SCANRUN_COMPARISON_EVIDENCE_APPLY/);
    assert.match(result.stdout, /only_comparison_evidence=yes/);
  } finally {
    server.close();
    rmSync(fixture.root, { recursive: true, force: true });
  }
});

test("a failed post-check restores the fetched ScanRun schema", async () => {
  const fixture = migrationFixture();
  const sha = "c".repeat(40);
  const before = localInventory((schema) => {
    delete schema.properties.comparison_evidence;
    return schema;
  });
  const puts = [];
  const server = createServer((request, response) => {
    const chunks = [];
    request.on("data", (chunk) => chunks.push(chunk));
    request.on("end", () => {
      if (request.method === "PUT") puts.push(JSON.parse(Buffer.concat(chunks).toString("utf8")).entity_schema);
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({
        schemas: Object.entries(before).map(([entity_name, entity_schema]) => ({ entity_name, entity_schema })),
      }));
    });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const auth = join(fixture.root, "auth.json");
  writeFileSync(auth, JSON.stringify({ accessToken: "z".repeat(40) }));
  try {
    const result = await run("bash", ["scripts/migrate-scanrun-comparison-evidence.sh"], {
      cwd: fixture.root,
      env: {
        ...process.env,
        ACTION: "apply",
        SOURCE_SHA: sha,
        CONFIRM: `APPLY-SCANRUN-COMPARISON-EVIDENCE:${sha}:77`,
        BARRIER_EXPECTED_GENERATION: "77",
        BARRIER_EXPECTED_PRIOR_MODE: "closed",
        CHANGE_TICKET: "incident-378",
        BASE44_EXPECTED_OWNER: "owner@example.com",
        BASE44_SCHEMA_API_FIXTURE: `http://127.0.0.1:${server.address().port}`,
        BASE44_AUTH_FILE: auth,
        BASE44_API_KEY: "",
        GITHUB_ACTIONS: "",
        TEST_OPERATOR_LOG: fixture.operatorLog,
      },
    });
    assert.equal(result.status, 1, result.stderr);
    assert.equal(puts.length, 2);
    assert.equal(Object.hasOwn(puts[0].properties, "comparison_evidence"), true);
    assert.equal(Object.hasOwn(puts[1].properties, "comparison_evidence"), false);
    assert.match(result.stderr, /SCHEMA_MIGRATION_PREIMAGE_RESTORED/);
  } finally {
    server.close();
    rmSync(fixture.root, { recursive: true, force: true });
  }
});

function migrationEnv(fixture, sha, confirm, port) {
  return {
    ...process.env,
    ACTION: confirm.startsWith("ROLLBACK") ? "rollback" : "apply",
    SOURCE_SHA: sha,
    CONFIRM: confirm,
    BARRIER_EXPECTED_GENERATION: "77",
    BARRIER_EXPECTED_PRIOR_MODE: "closed",
    CHANGE_TICKET: "incident-378",
    BASE44_EXPECTED_OWNER: "owner@example.com",
    BASE44_SCHEMA_API_FIXTURE: `http://127.0.0.1:${port}`,
    BASE44_AUTH_FILE: join(fixture.root, "auth.json"),
    BASE44_API_KEY: "",
    GITHUB_ACTIONS: "",
    TEST_OPERATOR_LOG: fixture.operatorLog,
    GCP_ADMISSION_OPERATOR_SERVICE_ACCOUNT: "fixlist-admission-operator@example.iam.gserviceaccount.com",
  };
}

function listen(handler) {
  const server = createServer(handler);
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}

test("a failed closed-barrier proof performs no schema write", async () => {
  const fixture = migrationFixture({ operatorExit: 1 });
  const sha = "d".repeat(40);
  const requests = [];
  const server = await listen((request, response) => {
    requests.push(request.method);
    response.writeHead(500);
    response.end("{}");
  });
  writeFileSync(join(fixture.root, "auth.json"), JSON.stringify({ accessToken: "d".repeat(40) }));
  try {
    const result = await run("bash", ["scripts/migrate-scanrun-comparison-evidence.sh"], {
      cwd: fixture.root,
      env: migrationEnv(fixture, sha, `APPLY-SCANRUN-COMPARISON-EVIDENCE:${sha}:77`, server.address().port),
    });
    assert.notEqual(result.status, 0);
    assert.deepEqual(requests, []);
  } finally {
    server.close();
    rmSync(fixture.root, { recursive: true, force: true });
  }
});

test("apply is refused with no write when comparison_evidence is already present", async () => {
  const fixture = migrationFixture();
  const sha = "e".repeat(40);
  const schemas = localInventory();
  const puts = [];
  const server = await listen((request, response) => {
    const chunks = [];
    request.on("data", (chunk) => chunks.push(chunk));
    request.on("end", () => {
      if (request.method === "PUT") puts.push(JSON.parse(Buffer.concat(chunks).toString("utf8")));
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({
        schemas: Object.entries(schemas).map(([entity_name, entity_schema]) => ({ entity_name, entity_schema })),
      }));
    });
  });
  writeFileSync(join(fixture.root, "auth.json"), JSON.stringify({ accessToken: "e".repeat(40) }));
  try {
    const result = await run("bash", ["scripts/migrate-scanrun-comparison-evidence.sh"], {
      cwd: fixture.root,
      env: migrationEnv(fixture, sha, `APPLY-SCANRUN-COMPARISON-EVIDENCE:${sha}:77`, server.address().port),
    });
    assert.equal(result.status, 2, `${result.stdout}\n${result.stderr}`);
    assert.match(result.stderr, /SCHEMA_MIGRATION_REFUSED action=apply decision=match/);
    assert.equal(puts.length, 0);
  } finally {
    server.close();
    rmSync(fixture.root, { recursive: true, force: true });
  }
});

test("rollback deletes only comparison_evidence after a clear row scan", async () => {
  const fixture = migrationFixture();
  const sha = "f".repeat(40);
  const schemas = localInventory((schema) => {
    schema.platform_marker = "live-only";
    schema.properties.created_date = { type: "string" };
    return schema;
  });
  let stored = structuredClone(schemas.ScanRun);
  const puts = [];
  const server = await listen((request, response) => {
    const chunks = [];
    request.on("data", (chunk) => chunks.push(chunk));
    request.on("end", () => {
      const url = new URL(request.url, "http://127.0.0.1");
      if (url.pathname.endsWith("/entities/ScanRun/v2/list")) {
        response.writeHead(200, { "content-type": "application/json" });
        response.end(JSON.stringify({
          items: [{ id: "empty-a", comparison_evidence: {} }, { id: "empty-b", comparison_evidence: null }],
          has_more: false,
        }));
        return;
      }
      if (request.method === "PUT") {
        const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
        puts.push(body.entity_schema);
        stored = body.entity_schema;
      }
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({
        schemas: Object.entries({ ...schemas, ScanRun: stored }).map(([entity_name, entity_schema]) => ({ entity_name, entity_schema })),
      }));
    });
  });
  writeFileSync(join(fixture.root, "auth.json"), JSON.stringify({ accessToken: "f".repeat(40) }));
  try {
    const result = await run("bash", ["scripts/migrate-scanrun-comparison-evidence.sh"], {
      cwd: fixture.root,
      env: migrationEnv(fixture, sha, `ROLLBACK-SCANRUN-COMPARISON-EVIDENCE:${sha}:77`, server.address().port),
    });
    assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
    assert.equal(puts.length, 1);
    assert.equal(Object.hasOwn(puts[0].properties, "comparison_evidence"), false);
    assert.equal(puts[0].platform_marker, "live-only");
    assert.deepEqual(puts[0].properties.created_date, { type: "string" });
    assert.match(result.stdout, /state=clear/);
    assert.match(result.stdout, /SCANRUN_COMPARISON_EVIDENCE_ROLLBACK/);
  } finally {
    server.close();
    rmSync(fixture.root, { recursive: true, force: true });
  }
});

test("rollback is refused with no write when a row already stores comparison evidence", async () => {
  const fixture = migrationFixture();
  const sha = "1".repeat(40);
  const schemas = localInventory();
  const puts = [];
  const server = await listen((request, response) => {
    const chunks = [];
    request.on("data", (chunk) => chunks.push(chunk));
    request.on("end", () => {
      const url = new URL(request.url, "http://127.0.0.1");
      if (request.method === "PUT") puts.push(JSON.parse(Buffer.concat(chunks).toString("utf8")));
      if (url.pathname.endsWith("/entities/ScanRun/v2/list")) {
        response.writeHead(200, { "content-type": "application/json" });
        response.end(JSON.stringify({
          items: [{ id: "kept", comparison_evidence: { version: "scan_comparison_evidence_v1_missing_h1" } }],
          has_more: false,
        }));
        return;
      }
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({
        schemas: Object.entries(schemas).map(([entity_name, entity_schema]) => ({ entity_name, entity_schema })),
      }));
    });
  });
  writeFileSync(join(fixture.root, "auth.json"), JSON.stringify({ accessToken: "1".repeat(40) }));
  try {
    const result = await run("bash", ["scripts/migrate-scanrun-comparison-evidence.sh"], {
      cwd: fixture.root,
      env: migrationEnv(fixture, sha, `ROLLBACK-SCANRUN-COMPARISON-EVIDENCE:${sha}:77`, server.address().port),
    });
    assert.equal(result.status, 2, `${result.stdout}\n${result.stderr}`);
    assert.match(result.stdout, /state=present/);
    assert.match(result.stderr, /stored comparison_evidence/);
    assert.equal(puts.length, 0);
  } finally {
    server.close();
    rmSync(fixture.root, { recursive: true, force: true });
  }
});

test("a stored comparison_evidence on an unfinished page cannot be overridden", async () => {
  const fixture = migrationFixture();
  const sha = "3".repeat(40);
  const schemas = localInventory();
  const puts = [];
  const lists = [];
  const server = await listen((request, response) => {
    const chunks = [];
    request.on("data", (chunk) => chunks.push(chunk));
    request.on("end", () => {
      const url = new URL(request.url, "http://127.0.0.1");
      if (request.method === "PUT") puts.push(JSON.parse(Buffer.concat(chunks).toString("utf8")));
      if (url.pathname.endsWith("/entities/ScanRun/v2/list")) {
        lists.push(url.search);
        if (url.searchParams.get("cursor")) {
          response.writeHead(500);
          response.end("{}");
          return;
        }
        response.writeHead(200, { "content-type": "application/json" });
        response.end(JSON.stringify({
          items: [{ id: "kept", comparison_evidence: { version: "scan_comparison_evidence_v1_missing_h1" } }],
          has_more: true,
          next_cursor: "page-2",
        }));
        return;
      }
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({
        schemas: Object.entries(schemas).map(([entity_name, entity_schema]) => ({ entity_name, entity_schema })),
      }));
    });
  });
  writeFileSync(join(fixture.root, "auth.json"), JSON.stringify({ accessToken: "3".repeat(40) }));
  try {
    const result = await run("bash", ["scripts/migrate-scanrun-comparison-evidence.sh"], {
      cwd: fixture.root,
      env: migrationEnv(fixture, sha, `ROLLBACK-SCANRUN-COMPARISON-EVIDENCE-UNVERIFIED-ROWS:${sha}:77`, server.address().port),
    });
    assert.equal(result.status, 2, `${result.stdout}\n${result.stderr}`);
    assert.match(result.stdout, /state=present/);
    assert.doesNotMatch(result.stdout, /state=unverified/);
    assert.match(result.stderr, /stored comparison_evidence/);
    assert.equal(puts.length, 0);
    assert.equal(lists.length, 1);
  } finally {
    server.close();
    rmSync(fixture.root, { recursive: true, force: true });
  }
});

test("every comparison_evidence page requests the field, and a missing key is not empty", async () => {
  const seen = [];
  const server = await listen((request, response) => {
    const url = new URL(request.url, "http://127.0.0.1");
    seen.push(`${url.pathname}${url.search}`);
    response.writeHead(200, { "content-type": "application/json" });
    if (!url.searchParams.get("cursor")) {
      response.end(JSON.stringify({
        items: [{ id: "a", comparison_evidence: {} }],
        has_more: true,
        next_cursor: "page-2",
      }));
      return;
    }
    response.end(JSON.stringify({
      items: [{ id: "b" }],
      has_more: false,
    }));
  });
  const root = mkdtempSync(join(tmpdir(), "evidence-pages-"));
  const auth = join(root, "auth.json");
  writeFileSync(auth, JSON.stringify({ accessToken: "p".repeat(40) }));
  try {
    const result = await run("node", ["scripts/base44_named_schema_client.mjs", "evidence-rows"], {
      env: {
        ...process.env,
        BASE44_SCHEMA_API_FIXTURE: `http://127.0.0.1:${server.address().port}`,
        BASE44_AUTH_FILE: auth,
        BASE44_API_KEY: "",
        GITHUB_ACTIONS: "",
      },
    });
    assert.equal(result.status, 4, `${result.stdout}\n${result.stderr}`);
    assert.match(result.stdout, /state=unverified reason=bad_item/);
    assert.equal(seen.length, 2);
    for (const url of seen) {
      assert.match(url, /fields=comparison_evidence/);
      assert.match(url, /limit=500/);
      assert.match(url, /sort=created_date/);
    }
    assert.match(seen[1], /cursor=page-2/);
  } finally {
    server.close();
    rmSync(root, { recursive: true, force: true });
  }
});

test("an unfinished row scan refuses rollback unless the unverified-rows confirmation is supplied", async () => {
  const fixture = migrationFixture();
  const sha = "2".repeat(40);
  const schemas = localInventory((schema) => {
    schema.platform_marker = "live-only";
    return schema;
  });
  let stored = structuredClone(schemas.ScanRun);
  const puts = [];
  const server = await listen((request, response) => {
    const chunks = [];
    request.on("data", (chunk) => chunks.push(chunk));
    request.on("end", () => {
      const url = new URL(request.url, "http://127.0.0.1");
      if (url.pathname.endsWith("/entities/ScanRun/v2/list")) {
        response.writeHead(503, { "content-type": "application/json" });
        response.end(JSON.stringify({ error: { code: "database_unavailable" } }));
        return;
      }
      if (request.method === "PUT") {
        const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
        puts.push(body.entity_schema);
        stored = body.entity_schema;
      }
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({
        schemas: Object.entries({ ...schemas, ScanRun: stored }).map(([entity_name, entity_schema]) => ({ entity_name, entity_schema })),
      }));
    });
  });
  writeFileSync(join(fixture.root, "auth.json"), JSON.stringify({ accessToken: "2".repeat(40) }));
  const port = server.address().port;
  try {
    const refused = await run("bash", ["scripts/migrate-scanrun-comparison-evidence.sh"], {
      cwd: fixture.root,
      env: migrationEnv(fixture, sha, `ROLLBACK-SCANRUN-COMPARISON-EVIDENCE:${sha}:77`, port),
    });
    assert.equal(refused.status, 2, refused.stderr);
    assert.match(refused.stdout, /state=unverified/);
    assert.equal(puts.length, 0);
    const allowed = await run("bash", ["scripts/migrate-scanrun-comparison-evidence.sh"], {
      cwd: fixture.root,
      env: migrationEnv(fixture, sha, `ROLLBACK-SCANRUN-COMPARISON-EVIDENCE-UNVERIFIED-ROWS:${sha}:77`, port),
    });
    assert.equal(allowed.status, 0, `${allowed.stdout}\n${allowed.stderr}`);
    assert.equal(puts.length, 1);
    assert.equal(puts[0].platform_marker, "live-only");
    assert.equal(Object.hasOwn(puts[0].properties, "comparison_evidence"), false);
  } finally {
    server.close();
    rmSync(fixture.root, { recursive: true, force: true });
  }
});

test("cloud operator exposes the read-only preflight and the closed-barrier migration separately", () => {
  for (const operation of [
    "verify-base44-v8-preflight",
    "apply-scanrun-comparison-evidence",
    "rollback-scanrun-comparison-evidence",
  ]) {
    assert.match(workflow, new RegExp(`- ${operation}\\n`));
  }
  const generic = workflow.slice(workflow.indexOf("\n  operate:\n"), workflow.indexOf("\n  verify-admission-identity:\n"));
  assert.match(generic, /inputs\.operation != 'verify-base44-v8-preflight'/);
  assert.match(generic, /inputs\.operation != 'apply-scanrun-comparison-evidence'/);
  assert.match(generic, /inputs\.operation != 'rollback-scanrun-comparison-evidence'/);

  const preflightJob = workflow.split("\n  verify-base44-v8-preflight:\n")[1].split("\n  migrate-scanrun-comparison-evidence:\n")[0];
  assert.match(preflightJob, /environment: fixlist-production-owner/);
  assert.match(preflightJob, /READONLY-BASE44-V8-PREFLIGHT:/);
  assert.match(preflightJob, /scripts\/base44-v8-preflight\.sh/);
  assert.doesNotMatch(preflightJob, /migrate-scanrun-comparison-evidence\.sh/);
  assert.match(preflight, /READONLY-BASE44-V8-PREFLIGHT:/);
  assert.doesNotMatch(preflight, /entities[[:space:]]+push|secrets set|named_schema_client\.mjs" put/);

  const migrationJob = workflow.split("\n  migrate-scanrun-comparison-evidence:\n")[1];
  const barrier = migrationJob.indexOf("Prove the closed barrier before any Base44 sign-in");
  const login = migrationJob.indexOf("Authenticate Base44 owner with ephemeral device code");
  const write = migrationJob.indexOf("Apply or roll back only ScanRun.comparison_evidence");
  assert.ok(barrier > -1 && login > barrier && write > login);
  assert.match(migrationJob, /VERIFY-ZERO-ADMISSION:/);
  assert.match(migrationJob, /ROLLBACK-SCANRUN-COMPARISON-EVIDENCE-UNVERIFIED-ROWS:/);
  assert.match(migrationJob, /GCP_ADMISSION_OPERATOR_SERVICE_ACCOUNT/);
  assert.match(migration, /verify-zero-admission-obligations/);
  assert.doesNotMatch(migration, /entities[[:space:]]+push|entityNameToSchema/);
  assert.doesNotMatch(`${preflightJob}\n${migrationJob}`, /versions access|secret_sha256|SCAN_EVIDENCE_SIGNING_KEY=/);
});
