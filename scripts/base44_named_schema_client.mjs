#!/usr/bin/env node
// Named Base44 entity-schema connector.
//
// Reads and replaces one authority schema through
// /api/apps/{app_id}/entity-schemas/{entity_name}. This is the schema API the
// deployment contract requires. It never calls the bulk entity sync, which
// replaces every entity and deletes remote entities missing from the local
// directory.

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { comparisonEvidenceIsEmpty } from "./base44_authority_schema.mjs";

const AUTHORITY_ENTITIES = ["ScanRun", "FixList", "FixItem"];
const STAGED_ENTITIES = [...AUTHORITY_ENTITIES, "Access"];
const STAGED_WRITE_ENTITIES = ["ScanRun", "FixItem", "Access"];
const PINNED_ORIGIN = "https://app.base44.com";

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exit(2);
}

function appId() {
  const value = process.env.BASE44_APP_ID || "6a498732ec779dfaaeab0e53";
  if (!/^[a-f0-9]{24}$/.test(value)) fail("Refusing Base44 schema request: app id is invalid.");
  return value;
}

function origin() {
  const fixture = process.env.BASE44_SCHEMA_API_FIXTURE || "";
  if (fixture) {
    if (process.env.GITHUB_ACTIONS === "true") {
      fail("Refusing Base44 schema request: fixture origin is not allowed on GitHub Actions.");
    }
    let url;
    try {
      url = new URL(fixture);
    } catch {
      fail("Refusing Base44 schema request: fixture origin is invalid.");
    }
    if (!["127.0.0.1", "localhost"].includes(url.hostname) || !["http:", "https:"].includes(url.protocol)) {
      fail("Refusing Base44 schema request: fixture origin must be a local test server.");
    }
    return url.origin;
  }
  const configured = process.env.BASE44_API_URL || PINNED_ORIGIN;
  if (configured !== PINNED_ORIGIN) {
    fail("Refusing Base44 schema request: API origin is not https://app.base44.com.");
  }
  return PINNED_ORIGIN;
}

function authHeaders() {
  const headers = { accept: "application/json" };
  const apiKey = process.env.BASE44_API_KEY || "";
  if (apiKey) {
    if (process.env.GITHUB_ACTIONS === "true") {
      fail("Refusing Base44 schema request: workspace API key auth is not used by the hosted owner session.");
    }
    headers.api_key = apiKey;
    return headers;
  }
  if (process.env.GITHUB_ACTIONS === "true" && process.env.BASE44_AUTH_FILE) {
    fail("Refusing Base44 schema request: auth-file override is not allowed on GitHub Actions.");
  }
  const file = process.env.BASE44_AUTH_FILE
    || path.join(os.homedir(), ".base44", "auth", "auth.json");
  let parsed;
  try {
    parsed = JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    fail("Refusing Base44 schema request: owner session is missing. Approve the device login first.");
  }
  const token = typeof parsed?.accessToken === "string" ? parsed.accessToken : "";
  if (token.length < 20 || token.includes("\n") || token.includes("\r")) {
    fail("Refusing Base44 schema request: owner session token is unusable.");
  }
  headers.authorization = `Bearer ${token}`;
  return headers;
}

function unwrapSchema(item) {
  if (!item || typeof item !== "object" || Array.isArray(item)) return null;
  if (item.entity_schema && typeof item.entity_schema === "object" && !Array.isArray(item.entity_schema)) {
    const name = String(item.entity_name || item.entity_schema.name || "");
    return name ? { name, schema: item.entity_schema } : null;
  }
  if (typeof item.name === "string" && item.properties && typeof item.properties === "object") {
    return { name: item.name, schema: item };
  }
  return null;
}

export function inventoryFromList(payload, entities = AUTHORITY_ENTITIES) {
  const rows = Array.isArray(payload?.schemas)
    ? payload.schemas
    : Array.isArray(payload)
      ? payload
      : null;
  if (!rows) return null;
  const schemas = {};
  for (const row of rows) {
    const unwrapped = unwrapSchema(row);
    if (unwrapped && entities.includes(unwrapped.name)) {
      if (schemas[unwrapped.name]) throw new Error(`Duplicate Base44 entity schema: ${unwrapped.name}`);
      schemas[unwrapped.name] = unwrapped.schema;
    }
  }
  return schemas;
}

async function request(method, pathname, body) {
  const headers = authHeaders();
  if (body) headers["content-type"] = "application/json";
  const response = await fetch(new URL(pathname, origin()), {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(20000),
  });
  const text = await response.text();
  let parsed = null;
  try {
    parsed = text ? JSON.parse(text) : null;
  } catch {
    parsed = null;
  }
  return { status: response.status, parsed };
}

function statusFailure(action, status, parsed) {
  const code = typeof parsed?.error?.code === "string" && /^[a-z0-9_]{1,80}$/.test(parsed.error.code)
    ? parsed.error.code
    : "schema_request_failed";
  fail(`Base44 schema ${action} failed: HTTP ${status} (${code}).`);
}

async function fetchInventory(destination, entities = AUTHORITY_ENTITIES) {
  const id = appId();
  const listed = await request("GET", `/api/apps/${id}/entity-schemas`);
  let schemas = listed.status === 200 ? inventoryFromList(listed.parsed, entities) : null;
  if (!schemas) {
    if (listed.status !== 200 && listed.status !== 404 && listed.status !== 405) {
      statusFailure("list", listed.status, listed.parsed);
    }
    schemas = {};
    for (const name of entities) {
      const one = await request("GET", `/api/apps/${id}/entity-schemas/${name}`);
      if (one.status !== 200) statusFailure(`read ${name}`, one.status, one.parsed);
      const unwrapped = unwrapSchema(one.parsed) || unwrapSchema({ entity_name: name, entity_schema: one.parsed });
      if (!unwrapped || unwrapped.name !== name) fail(`Base44 schema read for ${name} did not return that entity.`);
      schemas[name] = unwrapped.schema;
    }
  }
  for (const name of entities) {
    if (!schemas[name]) fail(`Base44 schema inventory is missing ${name}.`);
  }
  fs.writeFileSync(destination, `${JSON.stringify({ schemas })}\n`);
  process.stdout.write(`SCHEMA_INVENTORY entities=${entities.join(",")}\n`);
}

// Project metadata only. Missing/looping pagination is never proof of no rows.
async function stagedRows(destination) {
  const fields = {
    ScanRun: "id,status,scan_mode,pipeline_mode,page_cap,pages_planned,last_committed_batch,workspace_cleanup_state,workspace_cleanup_completed_at",
    FixItem: "id,affected_page_count,affected_page_count_is_lower_bound,template_impact_estimates",
    Access: "id,page_cap",
  };
  const rows = {};
  for (const [name, projection] of Object.entries(fields)) {
    rows[name] = [];
    const seen = new Set();
    const seenIds = new Set();
    let cursor = "", complete = false;
    for (let page = 0; page < EVIDENCE_PAGE_CAP; page++) {
      const params = new URLSearchParams({fields: projection, limit: String(EVIDENCE_PAGE_LIMIT), sort: "created_date"});
      if (cursor) params.set("cursor", cursor);
      const result = await request("GET", `/api/apps/${appId()}/entities/${name}/v2/list?${params}`);
      const body = result.parsed;
      if (result.status !== 200 || !body || !Array.isArray(body.items) || typeof body.has_more !== "boolean"
          || body.items.some(item => !item || typeof item !== "object" || Array.isArray(item) || typeof item.id !== "string" || !item.id)) {
        throw new Error(`Staged rollback rows are unverified for ${name}`);
      }
      // A repeated row ID means the paginated inventory is not a trustworthy
      // complete set. Never interpret an overlapping cursor page as clearance.
      for (const item of body.items) {
        if (seenIds.has(item.id)) throw new Error(`Staged rollback rows duplicated ${name} ID`);
        seenIds.add(item.id);
      }
      rows[name].push(...body.items);
      if (!body.has_more) { complete = true; break; }
      if (typeof body.next_cursor !== "string" || !body.next_cursor || body.next_cursor.length > 8000 || seen.has(body.next_cursor)) {
        throw new Error(`Staged rollback pagination is unverified for ${name}`);
      }
      seen.add(body.next_cursor);
      cursor = body.next_cursor;
    }
    if (!complete) throw new Error(`Staged rollback row bound reached for ${name}`);
  }
  fs.writeFileSync(destination, `${JSON.stringify({complete: true, rows})}\n`, {mode: 0o600, flag: "wx"});
  process.stdout.write("STAGED_ROLLBACK_ROWS complete=true\n");
}

const EVIDENCE_PAGE_LIMIT = 500;
const EVIDENCE_PAGE_CAP = 40;

function unverifiedEvidence(reason) {
  const safe = String(reason || "unverified").replace(/[^a-z0-9_]/g, "").slice(0, 40) || "unverified";
  process.stdout.write(`SCANRUN_COMPARISON_EVIDENCE_ROWS state=unverified reason=${safe}\n`);
  process.exit(4);
}

function presentEvidence(pages, examined) {
  process.stdout.write(
    `SCANRUN_COMPARISON_EVIDENCE_ROWS state=present pages=${pages} examined=${examined} nonempty=1\n`,
  );
  process.exit(3);
}

// Read-only page through ScanRun. fields, limit, and sort go on every page,
// including cursor continuations, so a later page cannot drop the field and
// look empty. The first stored value exits 3 immediately. Exit 4 is only for
// a scan that has not yet seen a stored value and cannot be finished. A
// record that omits comparison_evidence after it was requested is not empty.
async function evidenceRows() {
  const id = appId();
  const seenCursors = new Set();
  let cursor = "";
  let pages = 0;
  let examined = 0;
  while (pages < EVIDENCE_PAGE_CAP) {
    const params = new URLSearchParams();
    params.set("fields", "comparison_evidence");
    params.set("limit", String(EVIDENCE_PAGE_LIMIT));
    params.set("sort", "created_date");
    if (cursor) params.set("cursor", cursor);
    let result;
    try {
      result = await request("GET", `/api/apps/${id}/entities/ScanRun/v2/list?${params}`);
    } catch {
      unverifiedEvidence("request_failed");
    }
    const page = result.parsed;
    if (result.status !== 200 || !page || !Array.isArray(page.items) || typeof page.has_more !== "boolean") {
      unverifiedEvidence(`http_${result.status}`);
    }
    pages += 1;
    for (const item of page.items) {
      if (!item || typeof item !== "object" || Array.isArray(item) || !Object.hasOwn(item, "comparison_evidence")) {
        unverifiedEvidence("bad_item");
      }
      examined += 1;
      if (!comparisonEvidenceIsEmpty(item.comparison_evidence)) presentEvidence(pages, examined);
    }
    if (!page.has_more) {
      process.stdout.write(
        `SCANRUN_COMPARISON_EVIDENCE_ROWS state=clear pages=${pages} examined=${examined} nonempty=0\n`,
      );
      process.exit(0);
    }
    const next = page.next_cursor;
    if (typeof next !== "string" || next.length < 1 || next.length > 8000 || seenCursors.has(next)) {
      unverifiedEvidence("bad_cursor");
    }
    seenCursors.add(next);
    cursor = next;
  }
  unverifiedEvidence("page_cap");
}

async function putScanRun(schemaFile, ENTITY_NAME = "ScanRun") {
  if (!STAGED_WRITE_ENTITIES.includes(ENTITY_NAME)) fail("Refusing schema update: entity is outside the staged write allowlist.");
  const schema = JSON.parse(fs.readFileSync(schemaFile, "utf8"));
  if (schema?.name !== ENTITY_NAME || !schema.properties || typeof schema.properties !== "object") {
    fail(`Refusing schema update: payload is not the ${ENTITY_NAME} entity schema.`);
  }
  if (Object.hasOwn(schema, "entityNameToSchema")) {
    fail("Refusing schema update: bulk entity sync payload is prohibited.");
  }
  const id = appId();
  const result = await request(
    "PUT",
    `/api/apps/${id}/entity-schemas/${ENTITY_NAME}`,
    { entity_schema: schema },
  );
  if (result.status !== 200) statusFailure(`update ${ENTITY_NAME}`, result.status, result.parsed);
  process.stdout.write(`SCHEMA_PUT entity=${ENTITY_NAME}\n`);
}

const invoked = process.argv[1] && fs.realpathSync(process.argv[1]) === fileURLToPath(import.meta.url);
if (invoked) {
  const command = process.argv[2] || "";
  const target = process.argv[3] || "";
  try {
    if (command === "evidence-rows") {
      await evidenceRows();
    } else if (command === "put-named") {
      if (!STAGED_WRITE_ENTITIES.includes(target) || !process.argv[4]) fail("Refusing named schema update: exact allowlisted entity and payload file required.");
      await putScanRun(process.argv[4], target);
    } else if (!target || target.includes("\0")) {
      fail("Refusing schema request: destination is missing.");
    } else if (command === "fetch") {
      await fetchInventory(target);
    } else if (command === "fetch-staged") {
      await fetchInventory(target, STAGED_ENTITIES);
    } else if (command === "staged-rows") {
      await stagedRows(target);
    } else if (command === "put") {
      await putScanRun(target);
    } else {
      fail("usage: fetch|fetch-staged <inventory.json> | put <scanrun-schema.json> | put-named <ScanRun|FixItem|Access> <schema.json> | staged-rows <rows.json> | evidence-rows");
    }
  } catch (error) {
    if (error && typeof error === "object" && error.code === "ERR_INVALID_URL") {
      fail("Refusing Base44 schema request: URL is invalid.");
    }
    fail(error instanceof Error ? error.message : "Base44 schema request failed.");
  }
}
