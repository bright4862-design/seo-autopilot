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

function generatedIdentities(logicalRoutes, occupied) {
  const generated = JSON.parse(readFileSync(new URL("../../data/generated-staged-v9-routes.json", import.meta.url), "utf8"));
  const { schema_version: schema, functions } = generated;
  if (schema !== "fixlist_staged_v9_routes_v1" || !isRecord(functions)
      || Object.keys(functions).length !== logicalRoutes.length) {
    throw new Error("invalid generated V9 route inventory");
  }
  return new Map(logicalRoutes.map((name) => {
    const { route_name: route, build_id: build, runtime_activation_id: activation, package_digest: digest } = functions[name] ?? {};
    if (typeof route !== "string" || route.length > 63 || !new RegExp(`^${name}B[0-9a-f]{16}$`).test(route) || occupied.includes(route)
        || !/^[0-9a-f]{64}$/.test(build) || !/^[A-Za-z0-9._-]{1,120}$/.test(activation)
        || !/^[0-9a-f]{64}$/.test(digest)) {
      throw new Error(`invalid generated identity for ${name}`);
    }
    return [route, [build, activation]];
  }));
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
  const identities = generation === "v9" ? generatedIdentities(active, aliases) : new Map();
  const [mode, route, ...extra] = process.argv.slice(2);
  if (mode === "--identity" && identities.has(route) && extra.length === 0) {
    process.stdout.write(`${identities.get(route).join(" ")}\n`);
  } else if (mode === undefined) {
    const deployed = generation === "v9" ? [...identities.keys(), ...retained] : active;
    process.stdout.write(`${[generation, ...deployed].join(" ")}\n`);
  } else {
    throw new Error("unknown active V9 release identity");
  }
} catch (error) {
  console.error(`Refusing public Base44 route manifest: ${error.message}.`);
  process.exitCode = 2;
}
