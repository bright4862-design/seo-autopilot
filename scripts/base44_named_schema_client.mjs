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

const ENTITY_NAME = "ScanRun";
const AUTHORITY_ENTITIES = ["ScanRun", "FixList", "FixItem"];
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

export function inventoryFromList(payload) {
  const rows = Array.isArray(payload?.schemas)
    ? payload.schemas
    : Array.isArray(payload)
      ? payload
      : null;
  if (!rows) return null;
  const schemas = {};
  for (const row of rows) {
    const unwrapped = unwrapSchema(row);
    if (unwrapped && AUTHORITY_ENTITIES.includes(unwrapped.name)) schemas[unwrapped.name] = unwrapped.schema;
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

async function fetchInventory(destination) {
  const id = appId();
  const listed = await request("GET", `/api/apps/${id}/entity-schemas`);
  let schemas = listed.status === 200 ? inventoryFromList(listed.parsed) : null;
  if (!schemas) {
    if (listed.status !== 200 && listed.status !== 404 && listed.status !== 405) {
      statusFailure("list", listed.status, listed.parsed);
    }
    schemas = {};
    for (const name of AUTHORITY_ENTITIES) {
      const one = await request("GET", `/api/apps/${id}/entity-schemas/${name}`);
      if (one.status !== 200) statusFailure(`read ${name}`, one.status, one.parsed);
      const unwrapped = unwrapSchema(one.parsed) || unwrapSchema({ entity_name: name, entity_schema: one.parsed });
      if (!unwrapped || unwrapped.name !== name) fail(`Base44 schema read for ${name} did not return that entity.`);
      schemas[name] = unwrapped.schema;
    }
  }
  for (const name of AUTHORITY_ENTITIES) {
    if (!schemas[name]) fail(`Base44 schema inventory is missing ${name}.`);
  }
  fs.writeFileSync(destination, `${JSON.stringify({ schemas })}\n`);
  process.stdout.write(`SCHEMA_INVENTORY entities=${AUTHORITY_ENTITIES.join(",")}\n`);
}

const EVIDENCE_PAGE_LIMIT = 500;
const EVIDENCE_PAGE_CAP = 40;

function unverifiedEvidence(reason) {
  const safe = String(reason || "unverified").replace(/[^a-z0-9_]/g, "").slice(0, 40) || "unverified";
  process.stdout.write(`SCANRUN_COMPARISON_EVIDENCE_ROWS state=unverified reason=${safe}\n`);
  process.exit(4);
}

// Read-only page through ScanRun. Only comparison_evidence is requested.
// A finished list with no stored value exits 0. Any stored value exits 3.
// A list that cannot be finished exits 4 and must not be treated as proof.
async function evidenceRows() {
  const id = appId();
  const seenCursors = new Set();
  let cursor = "";
  let pages = 0;
  let examined = 0;
  let nonempty = 0;
  while (pages < EVIDENCE_PAGE_CAP) {
    const params = new URLSearchParams();
    if (cursor) {
      params.set("cursor", cursor);
    } else {
      params.set("fields", "comparison_evidence");
      params.set("limit", String(EVIDENCE_PAGE_LIMIT));
      params.set("sort", "created_date");
    }
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
      if (!item || typeof item !== "object" || Array.isArray(item)) unverifiedEvidence("bad_item");
      examined += 1;
      if (!comparisonEvidenceIsEmpty(item.comparison_evidence)) nonempty += 1;
    }
    if (!page.has_more) {
      const state = nonempty > 0 ? "present" : "clear";
      process.stdout.write(
        `SCANRUN_COMPARISON_EVIDENCE_ROWS state=${state} pages=${pages} examined=${examined} nonempty=${nonempty}\n`,
      );
      process.exit(nonempty > 0 ? 3 : 0);
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

async function putScanRun(schemaFile) {
  const schema = JSON.parse(fs.readFileSync(schemaFile, "utf8"));
  if (schema?.name !== ENTITY_NAME || !schema.properties || typeof schema.properties !== "object") {
    fail("Refusing schema update: payload is not the ScanRun entity schema.");
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
  if (result.status !== 200) statusFailure("update ScanRun", result.status, result.parsed);
  process.stdout.write("SCHEMA_PUT entity=ScanRun\n");
}

const invoked = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (invoked) {
  const command = process.argv[2] || "";
  const target = process.argv[3] || "";
  try {
    if (command === "evidence-rows") {
      await evidenceRows();
    } else if (!target || target.includes("\0")) {
      fail("Refusing schema request: destination is missing.");
    } else if (command === "fetch") {
      await fetchInventory(target);
    } else if (command === "put") {
      await putScanRun(target);
    } else {
      fail("usage: fetch <inventory.json> | put <scanrun-schema.json> | evidence-rows");
    }
  } catch (error) {
    if (error && typeof error === "object" && error.code === "ERR_INVALID_URL") {
      fail("Refusing Base44 schema request: URL is invalid.");
    }
    fail(error instanceof Error ? error.message : "Base44 schema request failed.");
  }
}
