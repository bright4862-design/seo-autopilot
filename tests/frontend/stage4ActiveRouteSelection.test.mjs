import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  EXPECTED_SCANNER_FUNCTIONS,
  EXPECTED_SCANNER_ROUTE_GENERATION,
  SCANNER_RUNTIME_ROLES,
} from "../../scripts/stage4ReleaseAcceptance.mjs";

const manifest = JSON.parse(readFileSync(new URL("../../data/base44-function-routes.json", import.meta.url), "utf8"));

function assertPublicSelectionMatchesStage4(selection, expectedGeneration, expectedFunctions) {
  assert.equal(selection.schema_version, "base44_function_routes_v1");
  assert.equal(selection.generation.toUpperCase(), expectedGeneration,
    "Stage-4 release evidence must follow the publicly selected route generation");
  const activeRoutes = SCANNER_RUNTIME_ROLES.map((role) => selection.routes?.[role]);
  assert.equal(new Set(activeRoutes).size, SCANNER_RUNTIME_ROLES.length,
    "public route manifest must contain six distinct scanner roles");
  assert.deepEqual([...activeRoutes].sort(), [...expectedFunctions].sort(),
    "Stage-4 runtime identity requirements must cover the exact six public scanner routes");
}

test("Stage-4 identity requirements match the active public scanner route manifest", () => {
  assertPublicSelectionMatchesStage4(manifest, EXPECTED_SCANNER_ROUTE_GENERATION, EXPECTED_SCANNER_FUNCTIONS);
});

test("a future generation switch without changing Stage-4 is detectable", () => {
  const otherGeneration = manifest.generation === "v9" ? "v8" : "v9";
  const otherRoutes = manifest.historical_routes?.[otherGeneration] ?? manifest.candidate_routes?.[otherGeneration];
  assert.ok(otherRoutes, `missing ${otherGeneration} migration fixture in source manifest`);
  const selection = { ...manifest, generation: otherGeneration, routes: otherRoutes };
  assert.throws(() => assertPublicSelectionMatchesStage4(
    selection, EXPECTED_SCANNER_ROUTE_GENERATION, EXPECTED_SCANNER_FUNCTIONS,
  ), /publicly selected route generation/);
});

test("an individual scanner role cannot drift while generation stays unchanged", () => {
  const selection = {
    ...manifest,
    routes: { ...manifest.routes, getCustomerScanResult: "getCustomerScanResultV999" },
  };
  assert.throws(() => assertPublicSelectionMatchesStage4(
    selection, EXPECTED_SCANNER_ROUTE_GENERATION, EXPECTED_SCANNER_FUNCTIONS,
  ), /exact six public scanner routes/);
});
