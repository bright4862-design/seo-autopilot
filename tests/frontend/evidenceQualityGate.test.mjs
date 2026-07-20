import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const scanRunEntity = JSON.parse(readFileSync(new URL("../../base44/entities/ScanRun.jsonc", import.meta.url), "utf8"));

test("ScanRun stores evidence-quality authority fields", () => {
  for (const field of [
    "evidence_quality_state",
    "evidence_quality_score",
    "evidence_quality_reasons",
    "discovery_quality_state",
    "representative_html_page_count",
    "usable_html_page_count",
    "default_route_page_count",
    "evidence_quality_blocking",
    "evidence_quality_gate_version",
  ]) {
    assert.ok(scanRunEntity.properties[field], `ScanRun missing ${field}`);
  }
});
