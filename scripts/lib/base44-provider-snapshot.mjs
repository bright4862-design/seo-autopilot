import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { isDeepStrictEqual } from "node:util";

import { buildInputs, providerBuildDigest } from "./base44-provider-inputs.mjs";
import { captureFunctionInventory, functionInventoryDigest } from "./base44-pilot-inventory.mjs";
import { materializeStagedV9Packages } from "./staged-v9-function-packages.mjs";

const APP_ID = "6a498732ec779dfaaeab0e53";
const LEGACY_SOURCE = fs.readFileSync(new URL("../../data/published-pilot-legacy-source", import.meta.url), "utf8").trim();
const read = file => JSON.parse(fs.readFileSync(file, "utf8"));
const inventory = value => Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)));

export function prepareProviderSnapshot(source, legacy, capture, output, sourceSha, captureSha, mode) {
  if (!["preview", "checkpoint-input"].includes(mode) || ![sourceSha, captureSha].every(v => /^[a-f0-9]{40}$/.test(v))) {
    throw new Error("Invalid provider snapshot identity");
  }
  const routes = read(path.join(source, "data/base44-function-routes.json"));
  const candidate = read(path.join(source, "data/beta-crawler-revision.json"));
  const legacyRevision = read(path.join(legacy, "data/beta-crawler-revision.json"));
  if (routes.generation !== "v8" || candidate.status !== "candidate" || candidate.git_commit || candidate.acceptance_report
      || !/^([0-9a-f]{16})$/.test(legacyRevision.fingerprint)) throw new Error("Unexpected pilot or legacy release");
  const listing = fs.readFileSync(path.join(capture, "listed.txt"), "utf8");
  const expected = read(path.join(capture, "digests.json"));
  fs.mkdirSync(output, { mode: 0o700 });
  const scratch = fs.mkdtempSync(path.join(path.dirname(output), ".provider-packages-"));
  try {
    for (const relative of buildInputs) {
      const target = path.join(output, relative);
      fs.mkdirSync(path.dirname(target), { recursive: true });
      fs.cpSync(path.join(source, relative), target, { recursive: true });
    }
    const actual = captureFunctionInventory(capture, listing, output);
    if (!isDeepStrictEqual(inventory(expected), inventory(actual))) throw new Error("The captured inventory differs from its recorded digests");
    const vv = path.join(scratch, "v9");
    materializeStagedV9Packages(source, vv);
    const staged = read(path.join(source, "data/generated-staged-v9-routes.json")).functions;
    const retained = { ...actual };
    const replaced = [];
    const aliases = Object.entries(routes.routes);
    if (aliases.length !== 6 || Object.keys(staged).length !== 6) throw new Error("Expected six V8 and six V9 packages");
    function replacePackage(name, project, allowSourceV8) {
      const relative = path.join("base44/functions", name);
      const dir = path.join(project, relative);
      const target = path.join(output, relative);
      const wanted = functionInventoryDigest(dir, name);
      if (!Object.hasOwn(actual, name)) throw new Error("Missing captured package " + name);
      if (actual[name] !== wanted) {
        if (!allowSourceV8 || actual[name] !== functionInventoryDigest(path.join(source, relative), name)) {
          throw new Error("Unrecognized captured package " + name);
        }
        replaced.push(name);
      }
      fs.rmSync(target, { recursive: true });
      fs.cpSync(dir, target, { recursive: true });
      retained[name] = wanted;
    }
    for (const [key, alias] of aliases) {
      if (!/^[A-Za-z]+$/.test(key) || alias !== key + "V8") throw new Error("Invalid V8 alias");
      const pinned = staged[key + "V9"]?.route_name;
      if (!pinned || !new RegExp("^" + key + "V9B[0-9a-f]{16}$").test(pinned)) throw new Error("Invalid V9 alias");
      replacePackage(alias, legacy, true);
      replacePackage(pinned, vv, false);
    }
    // This frontend dependency is shared with a retained management package.
    const shared = "base44/functions/persistDurableScanAuthorityV7/evidenceUrlIdentity.js";
    if (!fs.readFileSync(path.join(source, shared)).equals(fs.readFileSync(path.join(output, shared)))) {
      throw new Error("The captured package changes the frontend evidence identity module");
    }
    if (!isDeepStrictEqual(inventory(retained), inventory(captureFunctionInventory(output, listing)))) {
      throw new Error("Output function inventory differs from the required packages");
    }
    const providerConfig = read(path.join(output, "base44/config.jsonc"));
    providerConfig.site.installCommand = "npm ci";
    fs.writeFileSync(path.join(output, "base44/config.jsonc"), JSON.stringify(providerConfig, null, 2) + "\n");
    fs.renameSync(path.join(output, "vite.config.js"), path.join(output, "vite.config.source.js"));
    fs.copyFileSync(fileURLToPath(new URL("./base44-provider-vite.mjs", import.meta.url)), path.join(output, "vite.config.js"));
    fs.mkdirSync(path.join(output, "scripts"));
    for (const name of ["base44-pilot-inventory.mjs", "base44-provider-inputs.mjs"]) {
      fs.copyFileSync(fileURLToPath(new URL(name, import.meta.url)), path.join(output, "scripts", name));
    }
    const manifest = {
      schema: "fixlist_provider_pilot_snapshot_v1", mode,
      scope: "frontend_build_inputs_and_captured_management_functions",
      activation: "separate_verified_serving_checkpoint_and_complete_rollback_required",
      app_id: APP_ID, source_sha: sourceSha, scan_function_generation: "PUBLISHED_PILOT",
      legacy_source_sha: LEGACY_SOURCE, legacy_fingerprint: legacyRevision.fingerprint, capture_source_sha: captureSha,
      capture_digest: createHash("sha256").update(JSON.stringify(inventory(actual))).digest("hex"),
      build_inputs_digest: providerBuildDigest(output), restored_v8: replaced.sort(), functions: inventory(retained),
    };
    fs.writeFileSync(path.join(output, "provider-snapshot.json"), JSON.stringify(manifest, null, 2) + "\n");
    return manifest;
  } catch (error) {
    fs.rmSync(output, { recursive: true, force: true });
    throw error;
  } finally {
    fs.rmSync(scratch, { recursive: true, force: true });
  }
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
  const snapshot = prepareProviderSnapshot(...process.argv.slice(2));
  console.log("PROVIDER_SNAPSHOT_PREPARED mode=%s source=%s functions=%s restored_v8=%s",
    snapshot.mode, snapshot.source_sha, Object.keys(snapshot.functions).length, snapshot.restored_v8.length);
}
