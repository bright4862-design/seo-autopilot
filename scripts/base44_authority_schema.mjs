#!/usr/bin/env node
// Semantic authority-schema parity for the three release entities.
//
// Byte identity with a Base44 pull is the post-deploy manifest check. Live
// schema reads are JSON, so this module compares the parsed contract: name,
// type, required fields, entity RLS, and each property. It ignores key order,
// platform row fields, an omitted JSON-Schema default that matches the local
// default, and omitted additionalProperties when the local value is true.
//
// The only migration this module will allow is adding the local
// ScanRun.comparison_evidence property. Every other difference is a refusal.

import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const REPO_ROOT = path.resolve(HERE, "..");
export const ENTITIES_DIR = path.join(REPO_ROOT, "base44", "entities");

export const AUTHORITY_ENTITIES = ["ScanRun", "FixList", "FixItem"];
export const COMPARISON_EVIDENCE_FIELD = "comparison_evidence";

// A stored row blocks rollback only when this field carries a value. Missing,
// null, blank text, and {} are the platform's empty states. Any other value,
// including an object with keys, is treated as evidence that must stay readable.
export function comparisonEvidenceIsEmpty(value) {
  if (value == null) return true;
  if (typeof value === "string") return value.trim() === "";
  if (Array.isArray(value)) return value.length === 0;
  if (typeof value === "object") return Object.keys(value).length === 0;
  return false;
}
export const SERVER_MANAGED_PROPERTIES = new Set([
  "id",
  "created_date",
  "updated_date",
  "created_by",
]);

export const SCANNER_FUNCTIONS = [
  "startStandardScanJobV8",
  "durableScanWorkerControlV8",
  "persistDurableScanAuthorityV8",
  "persistLimitedScanResultV8",
  "getCustomerScanResultV8",
  "deleteCustomerScanDataV8",
];

const HMAC_SEAL_VERSION = "scan_evidence_hmac_sha256_v1";

export function readJsonc(file) {
  const raw = fs.readFileSync(file, "utf8").replace(/^\s*\/\/.*$/gm, "");
  return JSON.parse(raw);
}

export function readLocalSchema(entityName, entitiesDir = ENTITIES_DIR) {
  const schema = readJsonc(path.join(entitiesDir, `${entityName}.jsonc`));
  if (schema.name !== entityName) {
    throw new Error(`${entityName}: local schema name does not match the file`);
  }
  return schema;
}

export function readLocalAuthoritySchemas(entitiesDir = ENTITIES_DIR) {
  return Object.fromEntries(AUTHORITY_ENTITIES.map((name) => [name, readLocalSchema(name, entitiesDir)]));
}

function canonicalize(value) {
  if (Array.isArray(value)) return value.map((item) => canonicalize(item));
  if (value && typeof value === "object") {
    const out = {};
    for (const key of Object.keys(value).sort()) out[key] = canonicalize(value[key]);
    return out;
  }
  return value;
}

function same(left, right) {
  return JSON.stringify(canonicalize(left)) === JSON.stringify(canonicalize(right));
}

function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : null;
}

// Compare one property without treating Base44's omission of a JSON-Schema
// default, or of additionalProperties:true, as a different contract.
export function normalizeProperty(localProperty, remoteProperty) {
  const local = asObject(localProperty) || {};
  const remote = asObject(remoteProperty) || {};
  const normalized = { ...remote };
  if (!Object.hasOwn(normalized, "default") && Object.hasOwn(local, "default")) {
    normalized.default = local.default;
  }
  if (!Object.hasOwn(normalized, "additionalProperties") && local.additionalProperties === true) {
    normalized.additionalProperties = true;
  }
  if (!Object.hasOwn(normalized, "description") && typeof local.description === "string") {
    normalized.description = local.description;
  }
  return normalized;
}

function requiredNames(schema) {
  return Array.isArray(schema?.required) ? [...schema.required].map(String).sort() : [];
}

export function diffEntity(entityName, localSchema, remoteSchema) {
  if (!asObject(localSchema) || !asObject(remoteSchema)) {
    return {
      entity: entityName,
      status: "missing",
      missing: [],
      unexpected: [],
      changed: [],
      topLevel: ["schema"],
    };
  }
  const localProps = asObject(localSchema.properties) || {};
  const remoteProps = asObject(remoteSchema.properties) || {};
  const missing = [];
  const unexpected = [];
  const changed = [];

  for (const key of Object.keys(localProps).sort()) {
    if (!Object.hasOwn(remoteProps, key)) {
      missing.push(key);
      continue;
    }
    const normalized = normalizeProperty(localProps[key], remoteProps[key]);
    if (!same(localProps[key], normalized)) changed.push(key);
  }
  for (const key of Object.keys(remoteProps).sort()) {
    if (!Object.hasOwn(localProps, key) && !SERVER_MANAGED_PROPERTIES.has(key)) unexpected.push(key);
  }

  const topLevel = [];
  if (String(localSchema.name || "") !== String(remoteSchema.name || entityName)) topLevel.push("name");
  if (String(localSchema.type || "") !== String(remoteSchema.type || "")) topLevel.push("type");
  if (!same(requiredNames(localSchema), requiredNames(remoteSchema))) topLevel.push("required");
  if (!same(localSchema.rls ?? null, remoteSchema.rls ?? null)) topLevel.push("rls");

  let status = "match";
  if (missing.length || unexpected.length || changed.length || topLevel.length) status = "drift";
  if (
    entityName === "ScanRun"
    && missing.length === 1
    && missing[0] === COMPARISON_EVIDENCE_FIELD
    && unexpected.length === 0
    && changed.length === 0
    && topLevel.length === 0
    && localProps[COMPARISON_EVIDENCE_FIELD]
  ) {
    status = "additive_comparison_evidence";
  }

  return { entity: entityName, status, missing, unexpected, changed, topLevel };
}

export function assessInventory(remoteSchemas, entitiesDir = ENTITIES_DIR) {
  const local = readLocalAuthoritySchemas(entitiesDir);
  const reports = AUTHORITY_ENTITIES.map((name) => diffEntity(name, local[name], remoteSchemas?.[name]));
  const byName = Object.fromEntries(reports.map((report) => [report.entity, report]));
  const othersMatch = byName.FixList.status === "match" && byName.FixItem.status === "match";
  const scan = byName.ScanRun.status;
  let decision = "refuse";
  if (scan === "match" && othersMatch) decision = "match";
  else if (scan === "additive_comparison_evidence" && othersMatch) decision = "apply";
  return { decision, reports };
}

export function schemaDigest(schema) {
  const bytes = Buffer.from(JSON.stringify(canonicalize(schema)));
  return {
    bytes: bytes.length,
    sha256: crypto.createHash("sha256").update(bytes).digest("hex"),
  };
}

export function approvedComparisonEvidenceProperty(entitiesDir = ENTITIES_DIR) {
  const property = readLocalSchema("ScanRun", entitiesDir).properties?.[COMPARISON_EVIDENCE_FIELD];
  if (!property || property.type !== "object" || property.additionalProperties !== true) {
    throw new Error("Local comparison_evidence property is not the approved object shape");
  }
  if (JSON.stringify(property.default) !== "{}") {
    throw new Error("Local comparison_evidence default is not an empty object");
  }
  if (property.rls?.write?.user_condition?.role !== "admin") {
    throw new Error("Local comparison_evidence write rule is not admin-only");
  }
  return structuredClone(property);
}

// Copy the live schema and change only comparison_evidence. Remote-only
// annotations, platform fields, and property text stay on the document that
// was fetched. The approved property is inserted as stored in source; it is
// not a second copy of the whole local entity.
export function mutateLiveScanRun(preimage, action, approvedProperty = approvedComparisonEvidenceProperty()) {
  if (!asObject(preimage) || !asObject(preimage.properties)) {
    throw new Error("Live ScanRun schema is not an object with properties");
  }
  const next = structuredClone(preimage);
  if (action === "apply") {
    if (Object.hasOwn(next.properties, COMPARISON_EVIDENCE_FIELD)) {
      throw new Error("Refusing apply: live ScanRun already has comparison_evidence");
    }
    next.properties[COMPARISON_EVIDENCE_FIELD] = structuredClone(approvedProperty);
    return next;
  }
  if (action === "rollback") {
    if (!Object.hasOwn(next.properties, COMPARISON_EVIDENCE_FIELD)) {
      throw new Error("Refusing rollback: live ScanRun has no comparison_evidence");
    }
    delete next.properties[COMPARISON_EVIDENCE_FIELD];
    return next;
  }
  throw new Error(`Refusing schema materialization for ${action}`);
}

export function liveDiffIsOnlyComparisonEvidence(before, after, action, approvedProperty = approvedComparisonEvidenceProperty()) {
  if (!asObject(before) || !asObject(after) || !asObject(before.properties) || !asObject(after.properties)) {
    return false;
  }
  const left = structuredClone(before);
  const right = structuredClone(after);
  if (action === "apply") {
    const added = right.properties[COMPARISON_EVIDENCE_FIELD];
    // Base44 may echo the new property without description, default, or
    // additionalProperties. Those omissions are the same contract.
    const echoed = normalizeProperty(approvedProperty, added);
    if (!added || Object.hasOwn(left.properties, COMPARISON_EVIDENCE_FIELD) || !same(echoed, approvedProperty)) {
      return false;
    }
    delete right.properties[COMPARISON_EVIDENCE_FIELD];
    return same(left, right);
  }
  if (action === "rollback") {
    if (!Object.hasOwn(left.properties, COMPARISON_EVIDENCE_FIELD) || Object.hasOwn(right.properties, COMPARISON_EVIDENCE_FIELD)) {
      return false;
    }
    delete left.properties[COMPARISON_EVIDENCE_FIELD];
    return same(left, right);
  }
  return false;
}

function formatReport(report) {
  return [
    "SCHEMA_PARITY",
    `entity=${report.entity}`,
    `status=${report.status}`,
    `missing=${report.missing.join(",")}`,
    `unexpected=${report.unexpected.join(",")}`,
    `changed=${report.changed.join(",")}`,
    `top_level=${report.topLevel.join(",")}`,
  ].join(" ");
}

export function loadRemoteInventory(file) {
  const value = JSON.parse(fs.readFileSync(file, "utf8"));
  const schemas = asObject(value?.schemas) || asObject(value);
  if (!schemas) throw new Error("Remote schema inventory is not an object");
  return schemas;
}

function printAssessment(file) {
  const assessment = assessInventory(loadRemoteInventory(file));
  for (const report of assessment.reports) process.stdout.write(`${formatReport(report)}\n`);
  process.stdout.write(`SCHEMA_DECISION ${assessment.decision}\n`);
  return assessment;
}

export function stripAnsi(text) {
  return String(text || "").replace(/\u001b\[[0-9;]*m/g, "");
}

// The pinned Base44 CLI prints one item per line. Checking arbitrary words in
// all CLI output can mistake errors or advisory text for deployed inventory.
// Preserve only complete, unadorned item lines (allowing whitespace and ANSI).
function inventoryLines(text) {
  return new Set(stripAnsi(text).split(/\r?\n/).map((line) => line.trim()).filter(Boolean));
}

export function functionInventoryProblems(text) {
  const names = inventoryLines(text);
  const problems = [];
  for (const name of SCANNER_FUNCTIONS) {
    if (!names.has(name)) problems.push(`${name}: missing from Base44 function inventory`);
  }
  return problems;
}

export function signingSecretPresence(text) {
  const clean = stripAnsi(text);
  if (/SCAN_EVIDENCE_SIGNING_KEY\s*=/.test(clean)) {
    return { present: false, problem: "secret list included a signing-key value" };
  }
  const present = inventoryLines(clean).has("SCAN_EVIDENCE_SIGNING_KEY");
  return {
    present,
    problem: present ? "" : "SCAN_EVIDENCE_SIGNING_KEY is absent from the Base44 secret name list",
  };
}

export function readSigningRef(service) {
  const containers = service?.spec?.template?.spec?.containers;
  if (!Array.isArray(containers) || containers.length === 0) return { error: "absent" };
  const env = Array.isArray(containers[0]?.env) ? containers[0].env : [];
  const item = env.find((entry) => entry?.name === "SCAN_EVIDENCE_SIGNING_KEY");
  if (!item) return { error: "absent" };
  if (Object.hasOwn(item, "value")) return { error: "plaintext" };
  const ref = item.valueFrom?.secretKeyRef || {};
  const name = String(ref.name || "");
  const version = String(ref.key || "");
  if (!/^[A-Za-z0-9_-]{1,120}$/.test(name)) return { error: "malformed" };
  if (!/^[0-9]+$/.test(version)) return { error: "unpinned" };
  return { name, version };
}

export function signingContinuity(services) {
  const refs = {};
  const problems = [];
  for (const [label, service] of Object.entries(services)) {
    const ref = readSigningRef(service);
    refs[label] = ref;
    if (ref.error) problems.push(`${label}: ${ref.error}`);
  }
  const ok = Object.values(refs).filter((ref) => !ref.error);
  if (ok.length === 3) {
    const [first] = ok;
    for (const ref of ok.slice(1)) {
      if (ref.name !== first.name || ref.version !== first.version) {
        problems.push("signing secret name or numeric version differs across worker, gateway, and coordinator");
        break;
      }
    }
  }
  return { ok: problems.length === 0, refs, problems };
}

function requiresHmacSha256(relative, root) {
  const text = fs.readFileSync(path.join(root, relative), "utf8");
  return text.includes("HMAC") && text.includes("SHA-256");
}

export function hmacContractProblems(root = REPO_ROOT) {
  const problems = [];
  const persistSeal = fs.readFileSync(
    path.join(root, "base44/functions/persistDurableScanAuthorityV8/authoritySeal.js"),
    "utf8",
  );
  if (!persistSeal.includes(`AUTHORITY_SEAL_VERSION = "${HMAC_SEAL_VERSION}"`) || !persistSeal.includes("SHA-256")) {
    problems.push(`persistDurableScanAuthorityV8: authority seal is not ${HMAC_SEAL_VERSION}`);
  }
  for (const relative of [
    "base44/functions/durableScanWorkerControlV8/authoritySeal.js",
    "base44/functions/getCustomerScanResultV8/projectionStage1Legacy.js",
    "base44/functions/persistLimitedScanResultV8/limitedResultIntegrity.js",
  ]) {
    if (!requiresHmacSha256(relative, root)) {
      problems.push(`${relative}: HMAC-SHA256 verifier is missing`);
    }
  }
  const python = fs.readFileSync(path.join(root, "scanner-api/app/authority_seal.py"), "utf8");
  if (!python.includes("hmac.new") || !python.includes("hashlib.sha256")) {
    problems.push("scanner-api/app/authority_seal.py: worker seal is not HMAC-SHA256");
  }
  for (const name of SCANNER_FUNCTIONS) {
    const contract = path.join(root, "base44/functions", name, "generatedReleaseContract.js");
    if (!fs.existsSync(contract)) {
      // Deletion does not seal a result, so it has no release-contract copy.
      // Every function that does seal must carry the same version.
      if (name !== "deleteCustomerScanDataV8") {
        problems.push(`${name}: generated release contract is missing`);
      }
      continue;
    }
    const text = fs.readFileSync(contract, "utf8");
    if (!text.includes(`"authority_seal_version": "${HMAC_SEAL_VERSION}"`)) {
      problems.push(`${name}: authority_seal_version is not ${HMAC_SEAL_VERSION}`);
    }
  }
  return problems;
}

export function localReleaseFingerprint(root = REPO_ROOT) {
  const text = fs.readFileSync(
    path.join(root, "base44/functions/persistDurableScanAuthorityV8/generatedReleaseContract.js"),
    "utf8",
  );
  const match = text.match(/export const RELEASE_FINGERPRINT = "([0-9a-f]{16})"/);
  if (!match) throw new Error("Local V8 release fingerprint is missing");
  return match[1];
}

function writeLiveMutation(action, preimageFile, destination) {
  const preimage = JSON.parse(fs.readFileSync(preimageFile, "utf8"));
  const schema = mutateLiveScanRun(preimage, action);
  fs.writeFileSync(destination, `${JSON.stringify(schema)}\n`);
  const digest = schemaDigest(schema);
  process.stdout.write(`SCHEMA_BYTES entity=ScanRun action=${action} sha256=${digest.sha256} bytes=${digest.bytes}\n`);
}

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exit(2);
}

const invoked = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (invoked) {
  const command = process.argv[2] || "";
  try {
    if (command === "classify" || command === "decide") {
      const assessment = printAssessment(process.argv[3]);
      const wanted = command === "decide" ? process.argv[4] : "";
      if (command === "classify") process.exit(assessment.decision === "match" ? 0 : 1);
      if (wanted !== "apply" && wanted !== "rollback") fail("decide requires apply or rollback");
      const allowed = (wanted === "apply" && assessment.decision === "apply")
        || (wanted === "rollback" && assessment.decision === "match");
      if (!allowed) {
        process.stderr.write(`SCHEMA_MIGRATION_REFUSED action=${wanted} decision=${assessment.decision}\n`);
        process.exit(2);
      }
      process.stdout.write(`SCHEMA_MIGRATION_ALLOWED action=${wanted}\n`);
    } else if (command === "verify-live") {
      const action = process.argv[3];
      const before = JSON.parse(fs.readFileSync(process.argv[4], "utf8"));
      const after = JSON.parse(fs.readFileSync(process.argv[5], "utf8"));
      const ok = liveDiffIsOnlyComparisonEvidence(before, after, action);
      process.stdout.write(`SCHEMA_LIVE_DIFF action=${action} only_comparison_evidence=${ok ? "yes" : "no"}\n`);
      process.exit(ok ? 0 : 1);
    } else if (command === "verify-others") {
      const assessment = assessInventory(loadRemoteInventory(process.argv[3]));
      const others = assessment.reports.filter((report) => report.entity !== "ScanRun");
      for (const report of others) process.stdout.write(`${formatReport(report)}\n`);
      const ok = others.length === 2 && others.every((report) => report.status === "match");
      process.stdout.write(`SCHEMA_OTHER_ENTITIES match=${ok ? "yes" : "no"}\n`);
      process.exit(ok ? 0 : 1);
    } else if (command === "write-live-mutation") {
      writeLiveMutation(process.argv[3], process.argv[4], process.argv[5]);
    } else if (command === "extract-scanrun") {
      const schemas = loadRemoteInventory(process.argv[3]);
      const schema = schemas.ScanRun;
      if (!schema || typeof schema !== "object" || !schema.properties) {
        fail("Remote inventory has no ScanRun schema to restore.");
      }
      if (schema.name && schema.name !== "ScanRun") fail("Remote ScanRun schema has a different name.");
      const preimage = { ...schema, name: "ScanRun" };
      fs.writeFileSync(process.argv[4], `${JSON.stringify(preimage)}\n`);
      process.stdout.write("SCHEMA_PREIMAGE entity=ScanRun\n");
    } else if (command === "function-inventory") {
      const problems = functionInventoryProblems(fs.readFileSync(process.argv[3], "utf8"));
      for (const name of SCANNER_FUNCTIONS) {
        const missing = problems.some((problem) => problem.startsWith(`${name}:`));
        process.stdout.write(`FUNCTION_INVENTORY name=${name} present=${missing ? "no" : "yes"}\n`);
      }
      if (problems.length) process.exit(1);
    } else if (command === "secret-present") {
      const result = signingSecretPresence(fs.readFileSync(process.argv[3], "utf8"));
      process.stdout.write(`BASE44_SIGNING_SECRET_PRESENT=${result.present ? "yes" : "no"}\n`);
      if (!result.present) {
        process.stderr.write(`${result.problem}\n`);
        process.exit(1);
      }
    } else if (command === "signing-refs") {
      const labels = ["worker", "gateway", "coordinator"];
      const services = {};
      labels.forEach((label, index) => {
        services[label] = JSON.parse(fs.readFileSync(process.argv[3 + index], "utf8"));
      });
      const result = signingContinuity(services);
      for (const label of labels) {
        const ref = result.refs[label];
        if (ref.error) process.stdout.write(`SIGNING_REF service=${label} state=${ref.error}\n`);
        else process.stdout.write(`SIGNING_REF service=${label} secret=${ref.name} version=${ref.version}\n`);
      }
      process.stdout.write(`SIGNING_CONTINUITY=${result.ok ? "match" : "mismatch"}\n`);
      if (!result.ok) {
        for (const problem of result.problems) process.stderr.write(`${problem}\n`);
        process.exit(1);
      }
    } else if (command === "hmac-contract") {
      const problems = hmacContractProblems();
      process.stdout.write(`HMAC_CONTRACT version=${HMAC_SEAL_VERSION} fingerprint=${localReleaseFingerprint()}\n`);
      if (problems.length) {
        for (const problem of problems) process.stderr.write(`${problem}\n`);
        process.exit(1);
      }
      process.stdout.write("HMAC_CONTRACT_SOURCE=match\n");
    } else {
      fail("usage: classify|decide|verify-live|verify-others|write-live-mutation|extract-scanrun|function-inventory|secret-present|signing-refs|hmac-contract");
    }
  } catch (error) {
    fail(error instanceof Error ? error.message : "schema parity failed");
  }
}
