from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one match in {path}, found {count}: {old[:100]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


path = "base44/functions/aiReviewScan/entry.ts"
replace_once(
    path,
    'const AI_REVIEW_VERSION = "aiReviewScan_v6_normalized_python_review_input";\nconst PYTHON_REVIEW_VERSION = "python_review_v1_archetype_templates";',
    'const AI_REVIEW_VERSION = "aiReviewScan_v7_current_python_compatibility";\nconst PYTHON_REVIEW_VERSION = "python_review_v2_structural_marketplace";\nconst PYTHON_REVIEW_CALIBRATION_VERSION = "review_evidence_calibration_v5_utility_redirect";',
)
replace_once(
    path,
    '''    if (reviewVersion !== PYTHON_REVIEW_VERSION) {
      return { ok: false, configured: true, reason: `Python review version mismatch: ${reviewVersion || "missing"}.` };
    }

    return { ok: true, configured: true, result };''',
    '''    if (reviewVersion !== PYTHON_REVIEW_VERSION) {
      return { ok: false, configured: true, reason: `Python review version mismatch: ${reviewVersion || "missing"}; expected ${PYTHON_REVIEW_VERSION}.` };
    }

    const calibrationVersion = result?.review_evidence_calibration_version || "";
    if (calibrationVersion !== PYTHON_REVIEW_CALIBRATION_VERSION) {
      return { ok: false, configured: true, reason: `Python review calibration mismatch: ${calibrationVersion || "missing"}; expected ${PYTHON_REVIEW_CALIBRATION_VERSION}.` };
    }

    return { ok: true, configured: true, result };''',
)

Path("tests/frontend/base44-python-compatibility.test.mjs").write_text('''import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const reviewFunction = readFileSync("base44/functions/aiReviewScan/entry.ts", "utf8");
const scanFunction = readFileSync("base44/functions/runAdvancedScan/entry.ts", "utf8");

test("Base44 accepts the deployed Python scanner, review, and calibration versions", () => {
  assert.match(scanFunction, /PYTHON_SCANNER_VERSION = "python_scanner_v3_bounded_request"/);
  assert.match(reviewFunction, /PYTHON_REVIEW_VERSION = "python_review_v2_structural_marketplace"/);
  assert.match(reviewFunction, /PYTHON_REVIEW_CALIBRATION_VERSION = "review_evidence_calibration_v5_utility_redirect"/);
});

test("Base44 rejects stale or uncalibrated Python review responses", () => {
  assert.match(reviewFunction, /reviewVersion !== PYTHON_REVIEW_VERSION/);
  assert.match(reviewFunction, /calibrationVersion !== PYTHON_REVIEW_CALIBRATION_VERSION/);
  assert.match(reviewFunction, /Python review calibration mismatch/);
});
''', encoding="utf-8")
