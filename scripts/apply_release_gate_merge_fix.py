from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one guarded match in {path}, found {count}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


scan_form = Path("src/components/scan/ScanWebsiteForm.jsx")
replace_once(
    scan_form,
    'import { buildAuthorityMarkers, buildDiagnosticAuthorityMarkers } from "@/lib/scanRunModel";',
    'import { buildAuthorityMarkers, buildDiagnosticAuthorityMarkers, buildScanRunFields } from "@/lib/scanRunModel";',
)
replace_once(
    scan_form,
    "  const authorityMarkers = buildAuthorityMarkers(scanData, aiData);\n  return {",
    "  const authorityMarkers = buildAuthorityMarkers(scanData, aiData);\n  const mergedRecord = {",
)
replace_once(
    scan_form,
    "    release_gate_eligible: aiData?.release_gate_eligible === false\n      ? false\n      : scanData?.release_gate_eligible === true && aiData?.release_gate_eligible === true,",
    "    // Scanner-stage eligibility is provisional because review authority markers do not exist yet.\n    // Preserve only an explicit Python Review rejection, then validate the completed record below.\n    release_gate_eligible: aiData?.release_gate_eligible !== false,",
)
replace_once(
    scan_form,
    "    raw: { scanner: slimScannerData(scanData), ai_review: slimAiData(aiData) },\n  };\n}\n\nfunction compressDebugData",
    "    raw: { scanner: slimScannerData(scanData), ai_review: slimAiData(aiData) },\n  };\n  return {\n    ...mergedRecord,\n    release_gate_eligible: buildScanRunFields(mergedRecord).release_gate_eligible,\n  };\n}\n\nfunction compressDebugData",
)

test_file = Path("tests/frontend/releaseAuthorityGate.test.mjs")
replace_once(
    test_file,
    'import assert from "node:assert/strict";\nimport test from "node:test";',
    'import assert from "node:assert/strict";\nimport { readFileSync } from "node:fs";\nimport test from "node:test";',
)
append_test = '''\n\ntest("the frontend re-evaluates the completed record instead of AND-ing the scanner-stage gate", () => {\n  const source = readFileSync(\n    new URL("../../src/components/scan/ScanWebsiteForm.jsx", import.meta.url),\n    "utf8"\n  );\n\n  assert.match(source, /const mergedRecord = \\{/);\n  assert.match(\n    source,\n    /release_gate_eligible: buildScanRunFields\\(mergedRecord\\)\\.release_gate_eligible/\n  );\n  assert.doesNotMatch(\n    source,\n    /scanData\\?\\.release_gate_eligible === true && aiData\\?\\.release_gate_eligible === true/\n  );\n});\n'''
text = test_file.read_text(encoding="utf-8")
if "the frontend re-evaluates the completed record" in text:
    raise RuntimeError("Regression test already exists; refusing to apply twice")
test_file.write_text(text.rstrip() + append_test, encoding="utf-8")

print("Applied guarded merged release-gate patch.")
