// Installed as vite.config.js only inside a generated provider checkpoint.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { isDeepStrictEqual } from "node:util";
import sourceConfig from "./vite.config.source.js";
import { providerBuildDigest } from "./scripts/base44-provider-inputs.mjs";
import { captureFunctionInventory } from "./scripts/base44-pilot-inventory.mjs";

const root = path.dirname(fileURLToPath(import.meta.url));
const manifest = JSON.parse(fs.readFileSync(path.join(root, "provider-snapshot.json"), "utf8"));
if (manifest.schema !== "fixlist_provider_pilot_snapshot_v1" || manifest.app_id !== "6a498732ec779dfaaeab0e53"
    || manifest.scan_function_generation !== "PUBLISHED_PILOT" || !/^[0-9a-f]{40}$/.test(manifest.source_sha)) {
  throw new Error("Invalid provider build identity");
}
if (providerBuildDigest(root) !== manifest.build_inputs_digest) throw new Error("Provider build inputs changed");
const names = Object.keys(manifest.functions);
const actual = captureFunctionInventory(root, names.map(name => "  " + name).join("\n"));
if (!isDeepStrictEqual({ ...actual }, manifest.functions)) throw new Error("Provider package inventory changed");
for (const [key, value] of Object.entries({
  VITE_BASE44_APP_ID: manifest.app_id,
  VITE_SCAN_FUNCTION_GENERATION: manifest.scan_function_generation,
  VITE_FIXLIST_SOURCE_SHA: manifest.source_sha,
})) {
  if (process.env[key] && process.env[key] !== value) throw new Error("Conflicting provider build input " + key);
  process.env[key] = value;
}
export default sourceConfig;
