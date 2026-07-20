from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one replacement, found {count}: {old!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


Path("src/lib/persistedScanRecord.js").write_text('''function persistedBoolean(persisted, key, fallback) {
  return typeof persisted?.[key] === "boolean" ? persisted[key] : fallback;
}

function persistedNumber(persisted, key, fallback = 0) {
  return persisted?.[key] == null ? Number(fallback || 0) : Number(persisted[key] || 0);
}

// Merge the durable ScanRun authority result into the quota-safe browser record.
// The preview arrays remain local and capped; persisted coverage and authority
// fields are copied exactly and must never be re-inferred from pages.length.
export function mergePersistedScanRunRecord(localRecord = {}, persistedScanRun = {}, fixListId = "") {
  const stableScanId = persistedScanRun?.id
    || localRecord?.scan_id
    || localRecord?.scan_run_id
    || localRecord?.id
    || "";
  const resolvedFixListId = fixListId
    || persistedScanRun?.fix_list_id
    || localRecord?.fix_list_id
    || "";

  return {
    ...localRecord,
    ...persistedScanRun,
    id: stableScanId,
    scan_id: stableScanId,
    scan_run_id: stableScanId,
    fix_list_id: resolvedFixListId,
    pages_found: persistedNumber(persistedScanRun, "pages_found", localRecord?.pages_found),
    pages_crawled: persistedNumber(persistedScanRun, "pages_crawled", localRecord?.pages_crawled),
    pages_retained: persistedNumber(persistedScanRun, "pages_retained", localRecord?.pages_retained),
    local_cache_complete: persistedBoolean(
      persistedScanRun,
      "local_cache_complete",
      localRecord?.local_cache_complete === true,
    ),
    release_gate_eligible: persistedBoolean(
      persistedScanRun,
      "release_gate_eligible",
      localRecord?.release_gate_eligible === true,
    ),
    score_is_provisional: persistedBoolean(
      persistedScanRun,
      "score_is_provisional",
      localRecord?.score_is_provisional === true,
    ),
    status: persistedScanRun?.status || localRecord?.status || "",
    scan_status: persistedScanRun?.scan_status || localRecord?.scan_status || "",
    beta_revision_fingerprint: persistedScanRun?.beta_revision_fingerprint
      || localRecord?.beta_revision_fingerprint
      || "",
  };
}
''', encoding="utf-8")

scan_runs = "src/lib/scanRuns.js"
replace_once(
    scan_runs,
    '''    await base44.entities.ScanRun.update(handle.id, {
      ...buildScanRunFields(mergedRecord, { status: deriveTerminalStatus(mergedRecord) }),
      fix_list_id: fixList.id,
      completed_at: new Date().toISOString(),
    });
    return fixList.id;''',
    '''    const completedAt = new Date().toISOString();
    const scanRunFields = {
      ...buildScanRunFields(mergedRecord, { status: deriveTerminalStatus(mergedRecord) }),
      fix_list_id: fixList.id,
      completed_at: completedAt,
    };
    const updatedRun = await base44.entities.ScanRun.update(handle.id, scanRunFields);
    return {
      fixListId: fixList.id,
      scanRun: {
        id: handle.id,
        ...scanRunFields,
        ...(updatedRun || {}),
      },
    };''',
)

form = "src/components/scan/ScanWebsiteForm.jsx"
replace_once(
    form,
    '''import { buildAuthorityMarkers, buildDiagnosticAuthorityMarkers, buildScanRunFields } from "@/lib/scanRunModel";
import { beginScanRun, completeScanRun, failScanRun, markScanRunReviewing } from "@/lib/scanRuns";''',
    '''import { mergePersistedScanRunRecord } from "@/lib/persistedScanRecord";
import { buildAuthorityMarkers, buildDiagnosticAuthorityMarkers, buildScanRunFields } from "@/lib/scanRunModel";
import { beginScanRun, completeScanRun, failScanRun, markScanRunReviewing } from "@/lib/scanRuns";''',
)
replace_once(
    form,
    '''      const durableRecord = normalizeScanRecordForStorage(mergedFinal);
      const fixListId = await completeScanRun(scanRunHandle, durableRecord).catch(() => null);
      if (fixListId) mergedFinal = { ...mergedFinal, fix_list_id: fixListId };
      saveScanForDashboard(mergedFinal, scanId);''',
    '''      const durableRecord = normalizeScanRecordForStorage(mergedFinal);
      const completion = await completeScanRun(scanRunHandle, durableRecord).catch(() => null);
      if (completion?.scanRun) {
        mergedFinal = mergePersistedScanRunRecord(
          mergedFinal,
          completion.scanRun,
          completion.fixListId,
        );
      } else if (completion?.fixListId) {
        mergedFinal = { ...mergedFinal, fix_list_id: completion.fixListId };
      }
      saveScanForDashboard(mergedFinal, mergedFinal?.scan_id || scanId);''',
)

Path("tests/frontend/persistedBrowserRecord.test.mjs").write_text('''import assert from "node:assert/strict";
import test from "node:test";

import { mergePersistedScanRunRecord } from "../../src/lib/persistedScanRecord.js";


test("persisted coverage and authority override the capped browser preview", () => {
  const pages = Array.from({ length: 12 }, (_, index) => ({ url: `/page-${index}` }));
  const result = mergePersistedScanRunRecord(
    {
      id: "local-id",
      scan_id: "local-id",
      pages,
      pages_crawled: 150,
      pages_found: 150,
      pages_retained: 12,
      local_cache_complete: false,
      release_gate_eligible: false,
      score_is_provisional: false,
      beta_revision_fingerprint: "candidate",
    },
    {
      id: "run-id",
      pages_crawled: 150,
      pages_found: 150,
      pages_retained: 150,
      local_cache_complete: true,
      release_gate_eligible: true,
      score_is_provisional: false,
      status: "complete",
      scan_status: "complete",
      beta_revision_fingerprint: "candidate",
      fix_list_id: "fix-list-id",
    },
  );

  assert.equal(result.id, "run-id");
  assert.equal(result.scan_id, "run-id");
  assert.equal(result.scan_run_id, "run-id");
  assert.equal(result.fix_list_id, "fix-list-id");
  assert.equal(result.pages.length, 12);
  assert.equal(result.pages_retained, 150);
  assert.equal(result.local_cache_complete, true);
  assert.equal(result.release_gate_eligible, true);
});


test("an explicit persisted veto cannot be overridden by a stale local true", () => {
  const result = mergePersistedScanRunRecord(
    {
      id: "run-id",
      release_gate_eligible: true,
      local_cache_complete: true,
      score_is_provisional: false,
    },
    {
      id: "run-id",
      release_gate_eligible: false,
      local_cache_complete: false,
      score_is_provisional: true,
      status: "limited",
      scan_status: "complete_with_access_limitations",
    },
  );

  assert.equal(result.release_gate_eligible, false);
  assert.equal(result.local_cache_complete, false);
  assert.equal(result.score_is_provisional, true);
  assert.equal(result.status, "limited");
  assert.equal(result.scan_status, "complete_with_access_limitations");
});


test("missing persisted fields preserve the local record without inferring from preview length", () => {
  const result = mergePersistedScanRunRecord(
    {
      id: "local-id",
      pages: [{ url: "/" }],
      pages_crawled: 40,
      pages_found: 50,
      pages_retained: 40,
      local_cache_complete: true,
      release_gate_eligible: false,
    },
    {},
  );

  assert.equal(result.pages.length, 1);
  assert.equal(result.pages_crawled, 40);
  assert.equal(result.pages_found, 50);
  assert.equal(result.pages_retained, 40);
  assert.equal(result.local_cache_complete, true);
  assert.equal(result.release_gate_eligible, false);
});
''', encoding="utf-8")

# Strengthen the source-contract test so future refactors cannot save the stale record.
test_path = "tests/frontend/releaseAuthorityGate.test.mjs"
replace_once(
    test_path,
    '''  assert.doesNotMatch(
    source,
    /scanData\?\.release_gate_eligible === true && aiData\?\.release_gate_eligible === true/
  );
});''',
    '''  assert.doesNotMatch(
    source,
    /scanData\?\.release_gate_eligible === true && aiData\?\.release_gate_eligible === true/
  );
  assert.match(source, /mergePersistedScanRunRecord\(/);
  assert.match(source, /saveScanForDashboard\(mergedFinal, mergedFinal\?\.scan_id \|\| scanId\)/);
});''',
)

# Update the existing durable FixList UX source contract to the new return envelope.
ux_test_path = "tests/frontend/fixListEvidenceUx.test.mjs"
replace_once(
    ux_test_path,
    '''test("returned durable fix_list_id is written into the browser scan record", () => {
  assert.match(scanFormSource, /const fixListId = await completeScanRun/);
  assert.match(scanFormSource, /fix_list_id: fixListId/);
  assert.match(scanFormSource, /meta_description_state/);
  assert.match(scanFormSource, /metadata_evidence_version/);
  assert.match(scanFormSource, /title_evidence_version/);
});''',
    '''test("returned durable ScanRun authority is written into the browser scan record", () => {
  assert.match(scanFormSource, /const completion = await completeScanRun/);
  assert.match(scanFormSource, /mergePersistedScanRunRecord\(/);
  assert.match(scanFormSource, /completion\.fixListId/);
  assert.match(scanFormSource, /meta_description_state/);
  assert.match(scanFormSource, /metadata_evidence_version/);
  assert.match(scanFormSource, /title_evidence_version/);
});''',
)
