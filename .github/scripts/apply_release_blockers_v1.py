from __future__ import annotations

import hashlib
import json
from pathlib import Path

OLD_FINGERPRINT = "db8b916f3bd6d09c"
CANONICAL_RESOLUTION_VERSION = "canonical_href_resolution_v1_hostless_same_path"


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one locator, found {count}: {old[:100]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# 1. Resolve Hartzler's malformed //chocolate-milk/ canonical as the current
# page path only when reconstructing the single-label authority exactly matches
# the final page path. Real scheme-relative domains remain untouched.
extract_path = Path("scanner-api/app/extract.py")
extract_text = extract_path.read_text(encoding="utf-8")
resolver = f'''CANONICAL_HREF_RESOLUTION_VERSION = "{CANONICAL_RESOLUTION_VERSION}"


def _canonical_path_key(value: str) -> str:
    path = str(value or "/").split("?", 1)[0].split("#", 1)[0]
    return path.rstrip("/") or "/"


def resolve_canonical_href(base_url: str, href: str) -> str:
    """Resolve canonical hrefs without turning a same-path slug into a fake host.

    Some HTML generators emit a root-relative canonical as ``//slug/``. URL
    joining normally interprets that as a scheme-relative host. We only repair
    the value when the authority is a single label and rebuilding it as a path
    exactly matches the final page path. Genuine scheme-relative domains keep
    normal URL semantics and remain eligible for cross-domain validation.
    """
    raw = str(href or "").strip()
    if not raw:
        return ""
    if raw.startswith("//"):
        candidate = urlparse(raw)
        base = urlparse(str(base_url or ""))
        hostname = (candidate.hostname or "").lower().strip(".")
        reconstructed_path = f"/{{hostname}}{{candidate.path or ''}}"
        is_plain_single_label = bool(hostname) and "." not in hostname and candidate.netloc.lower() == hostname
        if (
            is_plain_single_label
            and candidate.query == base.query
            and _canonical_path_key(reconstructed_path) == _canonical_path_key(base.path or "/")
        ):
            return base._replace(
                path=reconstructed_path,
                query=candidate.query,
                fragment=candidate.fragment,
            ).geturl()
    return urljoin(base_url, raw)


'''
locator = "def clean_text(value: str) -> str:\n"
if extract_text.count(locator) != 1:
    raise SystemExit("extract.py: clean_text locator mismatch")
extract_text = extract_text.replace(locator, resolver + locator, 1)
old_canonical = '        canonical = urljoin(final_url, canonical_tag.get("href", ""))'
new_canonical = '        canonical = resolve_canonical_href(final_url, canonical_tag.get("href", ""))'
if extract_text.count(old_canonical) != 1:
    raise SystemExit("extract.py: canonical urljoin locator mismatch")
extract_text = extract_text.replace(old_canonical, new_canonical, 1)
old_fields = '        "canonical": canonical,\n        "canonical_url": canonical,\n'
new_fields = (
    '        "canonical": canonical,\n'
    '        "canonical_url": canonical,\n'
    '        "canonical_href_resolution_version": CANONICAL_HREF_RESOLUTION_VERSION,\n'
)
if extract_text.count(old_fields) != 1:
    raise SystemExit("extract.py: canonical evidence fields locator mismatch")
extract_path.write_text(extract_text.replace(old_fields, new_fields, 1), encoding="utf-8")

# 2. Fingerprint the new extraction contract.
replace_once(
    "scanner-api/app/beta_revision.py",
    "    from .evidence_quality import EVIDENCE_QUALITY_GATE_VERSION\n",
    "    from .evidence_quality import EVIDENCE_QUALITY_GATE_VERSION\n"
    "    from .extract import CANONICAL_HREF_RESOLUTION_VERSION\n",
)
replace_once(
    "scanner-api/app/beta_revision.py",
    '        "canonical_target_evidence_version": CANONICAL_TARGET_EVIDENCE_VERSION,\n',
    '        "canonical_target_evidence_version": CANONICAL_TARGET_EVIDENCE_VERSION,\n'
    '        "canonical_href_resolution_version": CANONICAL_HREF_RESOLUTION_VERSION,\n',
)

revision_path = Path("data/beta-crawler-revision.json")
revision = json.loads(revision_path.read_text(encoding="utf-8"))
revision["component_versions"]["canonical_href_resolution_version"] = CANONICAL_RESOLUTION_VERSION
payload = json.dumps(revision["component_versions"], sort_keys=True, separators=(",", ":"))
new_fingerprint = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
revision["fingerprint"] = new_fingerprint
revision["acceptance_report"] = "docs/releases/release-authority-canonical-resolution-v1.md"
revision["note"] = (
    "Release-blocker candidate: compact browser authority imports the shared release contract, "
    "and hostless scheme-relative canonicals are repaired only when they reconstruct the same final page path."
)
revision_path.write_text(json.dumps(revision, indent=2, sort_keys=True) + "\n", encoding="utf-8")

# 3. Make the browser recovery layer consume the same release contract as
# durable ScanRun persistence, eliminating duplicated fingerprint literals.
model_path = Path("src/lib/scanRunModel.js")
model_text = model_path.read_text(encoding="utf-8")
old_contract = '''const CURRENT_SCANNER_VERSION = "python_scanner_v3_bounded_request";
const CURRENT_SCANNER_BUILD_REVISION = "hard_page_cap_response_v1";
const CURRENT_ARCHETYPE_CLASSIFIER_VERSION = "archetype_classifier_v9_local_business_hospitality";
const CURRENT_REVIEW_VERSION = "python_review_v2_structural_marketplace";
const CURRENT_CALIBRATION_VERSION = "review_evidence_calibration_v5_utility_redirect";
const CURRENT_BETA_REVISION_FINGERPRINT = "db8b916f3bd6d09c";
'''
new_contract = f'''export const RELEASE_AUTHORITY_CONTRACT = Object.freeze({{
  scannerVersion: "python_scanner_v3_bounded_request",
  scannerBuildRevision: "hard_page_cap_response_v1",
  archetypeClassifierVersion: "archetype_classifier_v9_local_business_hospitality",
  reviewVersion: "python_review_v2_structural_marketplace",
  calibrationVersion: "review_evidence_calibration_v5_utility_redirect",
  betaRevisionFingerprint: "{new_fingerprint}",
}});

const {{
  scannerVersion: CURRENT_SCANNER_VERSION,
  scannerBuildRevision: CURRENT_SCANNER_BUILD_REVISION,
  archetypeClassifierVersion: CURRENT_ARCHETYPE_CLASSIFIER_VERSION,
  reviewVersion: CURRENT_REVIEW_VERSION,
  calibrationVersion: CURRENT_CALIBRATION_VERSION,
  betaRevisionFingerprint: CURRENT_BETA_REVISION_FINGERPRINT,
}} = RELEASE_AUTHORITY_CONTRACT;
'''
if model_text.count(old_contract) != 1:
    raise SystemExit("scanRunModel.js: release contract locator mismatch")
model_path.write_text(model_text.replace(old_contract, new_contract, 1), encoding="utf-8")

recovery_path = Path("src/lib/scanStorageRecovery.js")
recovery_text = recovery_path.read_text(encoding="utf-8")
old_import = 'import { base44 } from "@/api/base44Client";\n'
new_import = (
    'import { base44 } from "@/api/base44Client";\n'
    'import { RELEASE_AUTHORITY_CONTRACT } from "@/lib/scanRunModel";\n'
)
if recovery_text.count(old_import) != 1:
    raise SystemExit("scanStorageRecovery.js: import locator mismatch")
recovery_text = recovery_text.replace(old_import, new_import, 1)
old_recovery_contract = '''const CURRENT_SCANNER_VERSION = "python_scanner_v3_bounded_request";
const CURRENT_SCANNER_BUILD_REVISION = "hard_page_cap_response_v1";
const CURRENT_ARCHETYPE_CLASSIFIER_VERSION = "archetype_classifier_v9_local_business_hospitality";
const CURRENT_REVIEW_VERSION = "python_review_v2_structural_marketplace";
const CURRENT_CALIBRATION_VERSION = "review_evidence_calibration_v5_utility_redirect";
const CURRENT_BETA_REVISION_FINGERPRINT = "52348dd1f3b77700";
'''
new_recovery_contract = '''const {
  scannerVersion: CURRENT_SCANNER_VERSION,
  scannerBuildRevision: CURRENT_SCANNER_BUILD_REVISION,
  archetypeClassifierVersion: CURRENT_ARCHETYPE_CLASSIFIER_VERSION,
  reviewVersion: CURRENT_REVIEW_VERSION,
  calibrationVersion: CURRENT_CALIBRATION_VERSION,
  betaRevisionFingerprint: CURRENT_BETA_REVISION_FINGERPRINT,
} = RELEASE_AUTHORITY_CONTRACT;
'''
if recovery_text.count(old_recovery_contract) != 1:
    raise SystemExit("scanStorageRecovery.js: stale authority contract locator mismatch")
recovery_path.write_text(recovery_text.replace(old_recovery_contract, new_recovery_contract, 1), encoding="utf-8")

# 4. Keep compatibility expectations aligned with the frozen revision.
for path in [
    "scanner-api/tests/test_observability.py",
    "tests/frontend/releaseAuthorityGate.test.mjs",
    "tests/frontend/scanRunPersistence.test.mjs",
]:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(OLD_FINGERPRINT)
    if count < 1:
        raise SystemExit(f"{path}: expected at least one old fingerprint")
    target.write_text(text.replace(OLD_FINGERPRINT, new_fingerprint), encoding="utf-8")

# 5. Production-shaped regressions.
canonical_test_path = Path("scanner-api/tests/test_canonical_origin_alias_equivalence.py")
canonical_tests = canonical_test_path.read_text(encoding="utf-8")
canonical_tests += f'''


def test_hostless_scheme_relative_same_path_canonical_uses_final_origin():
    page = extract_page(
        '<html><head><title>Chocolate Milk</title><link rel="canonical" href="//chocolate-milk/"></head><body><h1>Chocolate Milk</h1></body></html>',
        "https://hartzlerdairy.com/chocolate-milk",
        "https://www.hartzlerdairy.com/chocolate-milk/",
        200,
        "text/html",
        DISCOVERY,
    )

    assert page["canonical"] == "https://www.hartzlerdairy.com/chocolate-milk/"
    assert page["canonical_status"] == "self_or_equivalent"
    assert page["canonical_href_resolution_version"] == "{CANONICAL_RESOLUTION_VERSION}"
    assert not any(item["rule"] == "canonical_cross_domain" for item in build_findings([page]))


@pytest.mark.asyncio
async def test_real_scheme_relative_external_domain_remains_cross_domain():
    page = extract_page(
        '<html><head><title>Page</title><link rel="canonical" href="//canonical.example/chocolate-milk/"></head><body><h1>Page</h1></body></html>',
        "https://www.hartzlerdairy.com/chocolate-milk/",
        "https://www.hartzlerdairy.com/chocolate-milk/",
        200,
        "text/html",
        DISCOVERY,
    )

    assert page["canonical"] == "https://canonical.example/chocolate-milk/"
    assert page["canonical_status"] == "canonical_to_different_url"
    await validate_canonical_targets(
        FakeClient(),
        [page],
        RobotsPolicy("https://www.hartzlerdairy.com/robots.txt", "missing", 404),
    )
    assert page["canonical_target_state"] == "cross_domain_needs_verification"
    assert any(item["rule"] == "canonical_cross_domain" for item in build_findings([page]))
'''
canonical_test_path.write_text(canonical_tests, encoding="utf-8")

Path("tests/frontend/releaseAuthorityContract.test.mjs").write_text(f'''import assert from "node:assert/strict";
import {{ readFileSync }} from "node:fs";
import test from "node:test";

import {{ RELEASE_AUTHORITY_CONTRACT }} from "../../src/lib/scanRunModel.js";

const revision = JSON.parse(readFileSync(new URL("../../data/beta-crawler-revision.json", import.meta.url), "utf8"));
const recoverySource = readFileSync(new URL("../../src/lib/scanStorageRecovery.js", import.meta.url), "utf8");

test("compact recovery and durable persistence share one release authority contract", () => {{
  assert.equal(RELEASE_AUTHORITY_CONTRACT.betaRevisionFingerprint, revision.fingerprint);
  assert.equal(RELEASE_AUTHORITY_CONTRACT.archetypeClassifierVersion, revision.component_versions.archetype_classifier_version);
  assert.match(recoverySource, /import {{ RELEASE_AUTHORITY_CONTRACT }} from "@\\/lib\\/scanRunModel"/);
  assert.match(recoverySource, /betaRevisionFingerprint: CURRENT_BETA_REVISION_FINGERPRINT/);
  assert.doesNotMatch(recoverySource, /52348dd1f3b77700/);
  assert.doesNotMatch(recoverySource, /const CURRENT_BETA_REVISION_FINGERPRINT =/);
}});
''', encoding="utf-8")

Path("docs/releases/release-authority-canonical-resolution-v1.md").write_text(f'''# Release authority and canonical resolution v1

## Scope

- Compact browser recovery imports the same release-authority contract used by durable ScanRun persistence.
- A scheme-relative, single-label canonical is repaired as a local path only when reconstructing it exactly matches the page's final path.
- Genuine scheme-relative external domains remain cross-domain verification findings.

## Candidate

- Canonical href resolution: `{CANONICAL_RESOLUTION_VERSION}`
- Fingerprint: `{new_fingerprint}`

## Production acceptance

1. Hartzler `/chocolate-milk` has no `canonical_cross_domain` finding.
2. An authoritative control reports `release_gate_eligible: true` in compact browser diagnostics.
3. Lamanna remains provisional and reports `release_gate_eligible: false` for evidence-quality reasons.
''', encoding="utf-8")

print(f"fingerprint={{new_fingerprint}}")
print(f"canonical_href_resolution_version={{CANONICAL_RESOLUTION_VERSION}}")
