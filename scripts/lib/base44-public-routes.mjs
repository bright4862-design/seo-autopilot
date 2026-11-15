import { readFileSync } from "node:fs";

const CANONICAL_FUNCTIONS = [
  "startStandardScanJob",
  "durableScanWorkerControl",
  "persistDurableScanAuthority",
  "persistLimitedScanResult",
  "getCustomerScanResult",
  "deleteCustomerScanData",
];

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function exactRoutes(routes, generation) {
  if (!isRecord(routes) || Object.keys(routes).length !== CANONICAL_FUNCTIONS.length) {
    throw new Error(`${generation} must define all six scanner routes`);
  }
  return CANONICAL_FUNCTIONS.map((canonical) => {
    const alias = `${canonical}${generation.toUpperCase()}`;
    if (routes[canonical] !== alias) throw new Error(`${generation} must map ${canonical} to ${alias}`);
    return alias;
  });
}

// This resolver has no environment or CLI override. A publication can select
// V9 only by committing it as the active generation in the source manifest.
try {
  const manifest = JSON.parse(readFileSync(new URL("../../data/base44-function-routes.json", import.meta.url), "utf8"));
  const { schema_version: schema, generation, routes, historical_routes: historical = {}, candidate_routes: candidate = {} } = manifest;
  if (schema !== "base44_function_routes_v1" || !["v8", "v9"].includes(generation)) {
    throw new Error("unsupported route schema or active scanner generation");
  }
  if (!isRecord(historical) || !isRecord(candidate)) throw new Error("invalid historical or candidate route groups");
  const active = exactRoutes(routes, generation);
  const retained = generation === "v9" ? exactRoutes(historical.v8, "v8") : [];
  const groups = [routes, ...Object.values(historical), ...Object.values(candidate)];
  if (groups.some((group) => !isRecord(group))) throw new Error("invalid route group");
  const aliases = groups.flatMap((group) => Object.values(group));
  if (new Set(aliases).size !== aliases.length) throw new Error("duplicate function alias across route groups");
  process.stdout.write(`${[generation, ...active, ...retained].join(" ")}\n`);
} catch (error) {
  console.error(`Refusing public Base44 route manifest: ${error.message}.`);
  process.exitCode = 2;
}
