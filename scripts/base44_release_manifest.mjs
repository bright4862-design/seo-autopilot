#!/usr/bin/env node
// Base44 package integrity + deterministic release manifest.
//
// Two jobs:
//   1. verify   -- prove each function package is portable and self-contained
//   2. manifest -- emit exact function-package and authority-entity SHA-256
//                  hashes so a fresh Base44 pull can be compared byte-for-byte
//                  against this GitHub source
//
// Integrity rules enforced (each one has burned this repo at least once):
//   - function.jsonc "entry" must be a RELATIVE filename. The Base44 sandbox
//     normalizes it to a full repo path on its side; the source must stay
//     portable or a pulled package cannot be compared or redeployed.
//   - the import tree must be CLOSED: every relative import resolves to a file
//     inside the function directory, and every file in the directory is
//     reachable from the entry. Orphans ship dead bytes through the bundler.
//   - no import may ESCAPE the function directory ("../"). Base44 packages each
//     function alone; a parent import resolves at deploy time and fails at run
//     time.
//   - npm: imports must be VERSION PINNED, or one SHA deploys different bytes
//     on different days.
//   - no dynamic import() of a sibling module. The Base44 bundler has already
//     failed this resolution once (./httpResponse.js), producing a runtime
//     ReferenceError after a job was accepted.
//
// Usage:
//   node scripts/base44_release_manifest.mjs verify
//   node scripts/base44_release_manifest.mjs manifest [> release-manifest.json]
//   node scripts/base44_release_manifest.mjs compare <pulled-functions-dir> <pulled-entities-dir>

import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

const FUNCTIONS_DIR = "base44/functions";
const ENTITIES_DIR = "base44/entities";

export const RELEASE_FUNCTIONS = [
  "startStandardScanJobV2",
  "durableScanWorkerControlV2",
  "persistDurableScanAuthorityV2",
  "persistLimitedScanResultV2",
  "getCustomerScanResultV2",
  "deleteCustomerScanDataV2",
  "createAccessCheckout",
  "stripeWebhook",
  "ownerScanDebugControl",
];

export const RELEASE_ENTITIES = [
  "ScanRun",
  "FixList",
  "FixItem",
];

// Bare specifiers the Base44 runtime provides. Not resolvable on disk and not
// expected to be.
const RUNTIME_SPECIFIERS = [/^npm:/, /^base44:/, /^node:/, /^https?:/];

const STATIC_IMPORT = /(?:^|\n)\s*import\s+(?:[\s\S]*?\s+from\s+)?["']([^"']+)["']/g;
const EXPORT_FROM = /(?:^|\n)\s*export\s+[\s\S]*?\s+from\s+["']([^"']+)["']/g;
const DYNAMIC_IMPORT = /\bimport\s*\(\s*["']([^"']+)["']\s*\)/g;

function readJsonc(file) {
  const raw = fs.readFileSync(file, "utf8").replace(/^\s*\/\/.*$/gm, "");
  return JSON.parse(raw);
}

function specifiersIn(source, re) {
  const out = [];
  let m;
  re.lastIndex = 0;
  while ((m = re.exec(source))) out.push(m[1]);
  return out;
}

function isRuntimeSpecifier(spec) {
  return RUNTIME_SPECIFIERS.some((re) => re.test(spec));
}

export function auditFunction(fnName) {
  const dir = path.join(FUNCTIONS_DIR, fnName);
  const problems = [];

  if (!fs.existsSync(dir)) {
    return { fnName, problems: [`${fnName}: function directory is missing`], files: [], entry: null };
  }

  const configPath = path.join(dir, "function.jsonc");
  if (!fs.existsSync(configPath)) {
    problems.push(`${fnName}: function.jsonc is missing`);
    return { fnName, problems, files: [], entry: null };
  }

  const config = readJsonc(configPath);
  const entry = String(config.entry || "");

  if (config.name !== fnName) {
    problems.push(`${fnName}: function.jsonc name "${config.name}" does not match its directory`);
  }
  if (!entry) {
    problems.push(`${fnName}: function.jsonc declares no entry`);
  } else if (entry.includes("/") || entry.startsWith(".")) {
    problems.push(
      `${fnName}: entry "${entry}" is not a portable relative filename. `
      + `Base44 rewrites this to a full path on its side; the source must stay a bare filename.`,
    );
  } else if (!fs.existsSync(path.join(dir, entry))) {
    problems.push(`${fnName}: entry "${entry}" does not exist`);
  }

  // Symlinks are rejected outright. Base44 packages the directory contents; a
  // symlink either dangles at deploy time or silently pulls bytes from outside
  // the package, which defeats both the closed-tree and the manifest guarantee.
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const dirent of entries) {
    if (dirent.isSymbolicLink()) {
      problems.push(`${fnName}/${dirent.name}: symlink in a function package`);
    }
  }
  const onDisk = entries
    .filter((d) => !d.isSymbolicLink())
    .map((d) => d.name)
    .filter((f) => fs.statSync(path.join(dir, f)).isFile());

  // Walk the import graph from the entry.
  const reachable = new Set();
  const queue = entry && fs.existsSync(path.join(dir, entry)) ? [entry] : [];
  if (queue.length) reachable.add(entry);

  while (queue.length) {
    const rel = queue.shift();
    const source = fs.readFileSync(path.join(dir, rel), "utf8");

    for (const spec of specifiersIn(source, DYNAMIC_IMPORT)) {
      if (isRuntimeSpecifier(spec)) continue;
      problems.push(
        `${fnName}/${rel}: dynamic import("${spec}") of a local module. `
        + `The Base44 bundler has failed this resolution before; use a static import.`,
      );
    }

    const specs = [
      ...specifiersIn(source, STATIC_IMPORT),
      ...specifiersIn(source, EXPORT_FROM),
    ];

    for (const spec of specs) {
      if (spec.startsWith("npm:")) {
        if (!/@\d+\.\d+\.\d+/.test(spec)) {
          problems.push(`${fnName}/${rel}: unpinned npm import "${spec}"`);
        }
        continue;
      }
      if (isRuntimeSpecifier(spec)) continue;

      if (!spec.startsWith(".")) {
        problems.push(`${fnName}/${rel}: non-relative local import "${spec}"`);
        continue;
      }
      if (spec.startsWith("../") || spec.includes("/../")) {
        problems.push(`${fnName}/${rel}: import "${spec}" escapes the function directory`);
        continue;
      }

      const target = path.normalize(path.join(path.dirname(rel), spec));
      if (!fs.existsSync(path.join(dir, target))) {
        problems.push(`${fnName}/${rel}: import "${spec}" does not resolve to a file in the package`);
        continue;
      }
      if (!reachable.has(target)) {
        reachable.add(target);
        queue.push(target);
      }
    }
  }

  // Closure the other way: every shipped file must be reachable.
  for (const file of onDisk) {
    if (file === "function.jsonc") continue;
    if (!reachable.has(file)) {
      problems.push(
        `${fnName}/${file}: present in the package but unreachable from the entry. `
        + `Orphans ship dead bytes through the bundler.`,
      );
    }
  }

  return { fnName, problems, files: onDisk.sort(), entry };
}

export function auditAll(fns = RELEASE_FUNCTIONS) {
  return fns.map(auditFunction);
}

export function buildManifest(
  fns = RELEASE_FUNCTIONS,
  functionsDir = FUNCTIONS_DIR,
  entitiesToHash = RELEASE_ENTITIES,
  entitiesDir = ENTITIES_DIR,
) {
  const functions = {};
  for (const fnName of fns) {
    const dir = path.join(functionsDir, fnName);
    const files = {};
    for (const file of fs.readdirSync(dir).sort()) {
      const full = path.join(dir, file);
      if (!fs.statSync(full).isFile()) continue;
      const bytes = fs.readFileSync(full);
      files[file] = {
        bytes: bytes.length,
        sha256: crypto.createHash("sha256").update(bytes).digest("hex"),
      };
    }
    // Package digest: hash of "name\0sha256" lines in sorted order. Stable
    // across checkouts and independent of filesystem metadata.
    const packageDigest = crypto.createHash("sha256").update(
      Object.entries(files).map(([n, m]) => `${n}\0${m.sha256}`).join("\n"),
    ).digest("hex");
    functions[fnName] = { entry: readJsonc(path.join(dir, "function.jsonc")).entry, files, packageDigest };
  }
  const functionDigest = crypto.createHash("sha256").update(
    Object.entries(functions).map(([n, f]) => `${n}\0${f.packageDigest}`).join("\n"),
  ).digest("hex");

  const entities = {};
  for (const entityName of entitiesToHash) {
    const file = `${entityName}.jsonc`;
    const full = path.join(entitiesDir, file);
    const bytes = fs.readFileSync(full);
    const schema = readJsonc(full);
    if (schema.name !== entityName) {
      throw new Error(`${file}: schema name "${schema.name}" does not match the release entity`);
    }
    entities[entityName] = {
      file,
      bytes: bytes.length,
      sha256: crypto.createHash("sha256").update(bytes).digest("hex"),
    };
  }
  const entityDigest = crypto.createHash("sha256").update(
    Object.entries(entities).map(([n, metadata]) => `${n}\0${metadata.sha256}`).join("\n"),
  ).digest("hex");
  const releaseDigest = crypto.createHash("sha256").update(
    `functions\0${functionDigest}\nentities\0${entityDigest}`,
  ).digest("hex");
  return { functions, entities, functionDigest, entityDigest, releaseDigest };
}

export function compareReleaseDirectories(remoteFunctionsDir, remoteEntitiesDir) {
  const remoteRoot = path.resolve(String(remoteFunctionsDir || ""));
  const remoteEntityRoot = path.resolve(String(remoteEntitiesDir || ""));
  const problems = [];
  if (!remoteFunctionsDir || !fs.existsSync(remoteRoot) || !fs.statSync(remoteRoot).isDirectory()) {
    return { ok: false, problems: ["pulled Base44 functions directory is missing"], local: null, remote: null };
  }
  if (!remoteEntitiesDir || !fs.existsSync(remoteEntityRoot) || !fs.statSync(remoteEntityRoot).isDirectory()) {
    return { ok: false, problems: ["pulled Base44 entities directory is missing"], local: null, remote: null };
  }
  for (const fnName of RELEASE_FUNCTIONS) {
    if (!fs.existsSync(path.join(remoteRoot, fnName))) {
      problems.push(`${fnName}: missing from pulled Base44 inventory`);
    }
  }
  for (const entityName of RELEASE_ENTITIES) {
    if (!fs.existsSync(path.join(remoteEntityRoot, `${entityName}.jsonc`))) {
      problems.push(`${entityName}: entity schema missing from pulled Base44 inventory`);
    }
  }
  if (problems.length) return { ok: false, problems, local: null, remote: null };

  const local = buildManifest(RELEASE_FUNCTIONS, FUNCTIONS_DIR);
  const remote = buildManifest(RELEASE_FUNCTIONS, remoteRoot, RELEASE_ENTITIES, remoteEntityRoot);
  for (const fnName of RELEASE_FUNCTIONS) {
    const localPackage = local.functions[fnName];
    const remotePackage = remote.functions[fnName];
    if (localPackage.packageDigest !== remotePackage.packageDigest) {
      problems.push(
        `${fnName}: deployed package digest ${remotePackage.packageDigest} does not match candidate ${localPackage.packageDigest}`,
      );
    }
  }
  for (const entityName of RELEASE_ENTITIES) {
    const localSchema = local.entities[entityName];
    const remoteSchema = remote.entities[entityName];
    if (localSchema.sha256 !== remoteSchema.sha256) {
      problems.push(
        `${entityName}: deployed entity digest ${remoteSchema.sha256} does not match candidate ${localSchema.sha256}`,
      );
    }
  }
  if (local.releaseDigest !== remote.releaseDigest) {
    problems.push(
      `release digest ${remote.releaseDigest} does not match candidate ${local.releaseDigest}`,
    );
  }
  return { ok: problems.length === 0, problems, local, remote };
}

const invokedDirectly = process.argv[1] && import.meta.url.endsWith(path.basename(process.argv[1]));
if (invokedDirectly) {
  const mode = process.argv[2] || "verify";
  if (mode === "manifest") {
    process.stdout.write(`${JSON.stringify(buildManifest(), null, 2)}\n`);
  } else if (mode === "compare") {
    const comparison = compareReleaseDirectories(process.argv[3], process.argv[4]);
    if (!comparison.ok) {
      for (const problem of comparison.problems) process.stdout.write(`FAIL ${problem}\n`);
      process.exit(1);
    }
    process.stdout.write(`OK   pulled Base44 function/entity inventory matches ${comparison.local.releaseDigest}\n`);
  } else {
    const results = auditAll();
    const problems = results.flatMap((r) => r.problems);
    for (const r of results) {
      const count = r.problems.length;
      process.stdout.write(`${count === 0 ? "OK  " : "FAIL"} ${r.fnName} (entry=${r.entry}, ${r.files.length} files)\n`);
      for (const p of r.problems) process.stdout.write(`       - ${p}\n`);
    }
    if (problems.length) {
      process.stdout.write(`\n${problems.length} integrity problem(s)\n`);
      process.exit(1);
    }
    process.stdout.write("\nAll release function packages are portable, closed, and pinned.\n");
  }
}
