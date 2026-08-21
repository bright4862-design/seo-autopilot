import { RELEASE_FINGERPRINT } from "../../src/lib/generatedReleaseContract.js";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  createAuthoritySeal,
  verifyAuthoritySeal,
} from "../../base44/functions/grokChat/authoritySeal.js";
import { buildAuthoritySnapshot } from "../../base44/functions/aiReviewScan/authoritySnapshot.js";
import { buildAuthoritySnapshot as buildDurableAuthoritySnapshot } from "../../base44/functions/persistDurableScanAuthority/authoritySnapshot.js";
import {
  authorityRowsFromSnapshot,
  missingAuthorityFixRows,
} from "../../base44/functions/persistScanAuthority/authorityRows.js";
import { authorityRowsFromSnapshot as durableAuthorityRowsFromSnapshot } from "../../base44/functions/persistDurableScanAuthority/authorityRows.js";
import { authoritySnapshotFromRows } from "../../base44/functions/grokChat/authoritySnapshot.js";

import {
  conversationMatchesGrokScan,
  createGrokSendGuard,
  grokWorkspaceIdentity,
  grokWorkspaceMatches,
  normalizeGrokDomain,
  resolveActiveGrokConversationId,
  selectGrokConversationForScan,
  selectLatestAuthoritativeGrokScan,
  sortGrokMessages,
} from "../../src/lib/grokChat.js";

const functionSource = readFileSync("base44/functions/grokChat/index.ts", "utf8");
const scannerFunctionSource = readFileSync("base44/functions/runAdvancedScan/entry.ts", "utf8");
const reviewFunctionSource = readFileSync("base44/functions/aiReviewScan/entry.ts", "utf8");
const persistenceFunctionSource = readFileSync("base44/functions/persistScanAuthority/index.ts", "utf8");
const durablePersistenceSource = readFileSync("base44/functions/persistDurableScanAuthority/index.ts", "utf8");
const durableWorkerSource = readFileSync("scanner-api/app/scan_job.py", "utf8");
const assistantSource = readFileSync("src/pages/Assistant.jsx", "utf8");
const scanFormSource = readFileSync("src/components/scan/ScanWebsiteForm.jsx", "utf8");
const appSource = readFileSync("src/App.jsx", "utf8");
const layoutSource = readFileSync("src/components/layout/DashboardLayout.jsx", "utf8");
// Canonical declarations. The identical grok-conversation/grok-message copies
// were removed: two files declaring the same entity name made every Base44 CLI
// command fail validation, including the site-only deploy.
const conversationSchema = JSON.parse(readFileSync("base44/entities/GrokConversation.jsonc", "utf8"));
const messageSchema = JSON.parse(readFileSync("base44/entities/GrokMessage.jsonc", "utf8"));
const scanRunSchema = JSON.parse(readFileSync("base44/entities/ScanRun.jsonc", "utf8"));
const fixListSchema = JSON.parse(readFileSync("base44/entities/FixList.jsonc", "utf8"));
const fixItemSchema = JSON.parse(readFileSync("base44/entities/FixItem.jsonc", "utf8"));

const scan = {
  id: "scan_current",
  owner_user_id: "owner_1",
  project_id: "project_1",
  website_url: "https://www.Example.com/path",
  status: "complete",
  release_gate_eligible: true,
  score_is_provisional: false,
  evidence_quality_blocking: false,
  beta_revision_fingerprint: "release_current",
  completed_at: "2026-08-01T10:00:00Z",
};

const conversation = {
  id: "conversation_current",
  owner_user_id: "owner_1",
  project_id: "project_1",
  scan_run_id: "scan_current",
  normalized_domain: "example.com",
  release_fingerprint: "release_current",
  last_message_at: "2026-08-01T11:00:00Z",
};

test("Grok entities are linked, immutable to clients, and owner-readable through RLS", () => {
  assert.equal(conversationSchema.name, "GrokConversation");
  assert.equal(messageSchema.name, "GrokMessage");

  for (const field of ["owner_user_id", "project_id", "scan_run_id", "normalized_domain", "release_fingerprint"]) {
    assert.ok(conversationSchema.required.includes(field), `conversation.${field}`);
    assert.ok(messageSchema.required.includes(field), `message.${field}`);
  }
  assert.ok(messageSchema.required.includes("conversation_id"));
  assert.deepEqual(messageSchema.properties.role.enum, ["user", "assistant"]);
  assert.equal(messageSchema.properties.content.maxLength, 12000);

  for (const schema of [conversationSchema, messageSchema]) {
    assert.equal(schema.rls.create.user_condition.role, "admin");
    assert.equal(schema.rls.update.user_condition.role, "admin");
    assert.ok(schema.rls.read.$or.some((rule) => rule["data.owner_user_id"] === "{{user.id}}"));
    assert.ok(schema.rls.delete.$or.some((rule) => rule["data.owner_user_id"] === "{{user.id}}"));
  }
});

test("grokChat authenticates and fetches all evidence through caller-scoped RLS", () => {
  assert.match(functionSource, /createClientFromRequest\(req\)/);
  assert.match(functionSource, /await base44\.auth\.me\(\)/);
  for (const entity of ["ScanRun", "BusinessProject", "FixList", "FixItem", "GrokConversation", "GrokMessage"]) {
    assert.match(functionSource, new RegExp(`base44\\.entities\\.${entity}`));
  }
  for (const entity of ["ScanRun", "BusinessProject", "FixList", "FixItem"]) {
    assert.doesNotMatch(functionSource, new RegExp(`asServiceRole\\.entities\\.${entity}`));
  }
  assert.match(functionSource, /assertOwnedBy\(scan, user/);
  assert.match(functionSource, /assertAuthoritativeScan\(authoritySnapshot\.scan\)/);
  assert.match(functionSource, /assertConversationIdentity\(conversation/);
  assert.match(functionSource, /project_domain_mismatch/);
  assert.match(functionSource, /fix_list_mismatch/);
});

test("server authority proof fields cannot be written by customer clients", () => {
  for (const field of ["authority_seal_version", "authority_sealed_at", "authority_proof"]) {
    assert.equal(scanRunSchema.properties[field].rls.write.user_condition.role, "admin", field);
  }
  assert.equal(scanRunSchema.properties.authority_proof.minLength, 64);
  assert.equal(scanRunSchema.properties.authority_proof.maxLength, 64);

  for (const [name, schema] of [["FixList", fixListSchema], ["FixItem", fixItemSchema]]) {
    const proof = schema.properties.authority_proof;
    assert.equal(proof.minLength, 64, `${name}.authority_proof minLength`);
    assert.equal(proof.maxLength, 64, `${name}.authority_proof maxLength`);
    assert.equal(proof.pattern, "^[a-f0-9]{64}$", `${name}.authority_proof pattern`);
    assert.equal(proof.rls.write.user_condition.role, "admin", `${name}.authority_proof write FLS`);
  }
});

test("authority seals are deterministic and reject any nested evidence mutation", async () => {
  const secret = "unit-test-authority-secret-that-is-never-deployed";
  const snapshot = {
    version: "standard_review_snapshot_hmac_v1",
    scan: { id: "scan_1", release_gate_eligible: true },
    recommendations: [{ fix_id: "fix_1", priority: "high" }],
  };
  const reordered = {
    recommendations: [{ priority: "high", fix_id: "fix_1" }],
    scan: { release_gate_eligible: true, id: "scan_1" },
    version: "standard_review_snapshot_hmac_v1",
  };
  const proof = await createAuthoritySeal(snapshot, secret);
  assert.equal(await verifyAuthoritySeal(snapshot, secret, proof), true);
  assert.equal(await verifyAuthoritySeal(reordered, secret, proof), true);
  assert.equal(await verifyAuthoritySeal({ ...snapshot, recommendations: [{ fix_id: "fix_1", priority: "low" }] }, secret, proof), false);
  assert.equal(await verifyAuthoritySeal(snapshot, "wrong-secret", proof), false);
});

test("Grok reconstruction stays compatible with canonical v2 durable authority", async () => {
  const v2 = "repair_contract_v2_shadow_calibrated";
  const priorityModel = "repair_priority_v2_technical_severity";
  const canonicalRepairs = [
    {
      fix_id: "fix_first", rule: "internal_link_redirect", category: "internal_link",
      issue_title: "Update homepage links to use their final URLs", affected_pages: ["https://example.com/"],
      priority: "high", repair_contract_version: v2, repair_priority_model_version: priorityModel,
      base_severity: "high", technical_severity_source: "rule_taxonomy", evidence_class: "confirmed_problem",
      action_priority: "fix_first", action_priority_score: 4310, priority_reason: "1 important checked page is affected.",
      canonical_action_rank: 1, repair_identity_version: "repair_identity_v2_technical",
      repair_fingerprint: "aaa111aaa111aaa111aaa111", repair_identity_state: "stable", repair_identity_stable: true,
      repair_surface: "shared_navigation", remediation_family: "replace_redirecting_internal_link",
      priority_context: { affected_checked: 1, checked_eligible: 1, shared_repair_confirmed: false },
    },
    {
      fix_id: "improve", rule: "missing_meta_description", category: "meta_description",
      issue_title: "Add a search description to this page", affected_pages: ["https://example.com/a"],
      priority: "medium", repair_contract_version: v2, repair_priority_model_version: priorityModel,
      base_severity: "medium", technical_severity_source: "rule_taxonomy", evidence_class: "improvement",
      action_priority: "improve", action_priority_score: 2310, priority_reason: "1 checked page is affected.",
      canonical_action_rank: 2, repair_identity_version: "repair_identity_v2_technical",
      repair_fingerprint: "bbb222bbb222bbb222bbb222", repair_identity_state: "stable", repair_identity_stable: true,
      repair_surface: "cms_field", remediation_family: "update_meta_description",
      priority_context: { affected_checked: 1, checked_eligible: 1, shared_repair_confirmed: false },
    },
  ];
  const snapshot = buildDurableAuthoritySnapshot({
    scan: {
      scanner_version: "python_scanner_v3_bounded_request", scanner_build_revision: "authenticated_health_probe_v1",
      scanner_wrapper_version: "runStandard150Scan_v1_python_required", advanced_scan_backend: "python_scanner_api",
      deno_fallback_used: false, beta_revision_fingerprint: RELEASE_FINGERPRINT,
      metadata_evidence_version: "metadata_v1", title_evidence_version: "title_v1",
      website_url: "https://example.com/", pages_found: 12, pages_crawled: 10,
    },
    review: {
      archetype_classifier_version: "archetype_classifier_v9_local_business_hospitality",
      review_version: "python_review_v2_structural_marketplace",
      review_evidence_calibration_version: "review_evidence_calibration_v6_health_score_v2",
      ai_review_backend: "python_review_api", python_review_fallback_used: false,
      release_gate_eligible: true, score_is_provisional: false, evidence_quality_blocking: false,
      beta_revision_fingerprint: RELEASE_FINGERPRINT, metadata_evidence_version: "metadata_v1", title_evidence_version: "title_v1",
      scan_status: "complete", health_score: 72, health_grade: "Needs attention",
      repair_contract_version: v2, repair_snapshot_contract_version: v2, repair_snapshot_contract_complete: true,
      repair_priority_model_version: priorityModel, canonical_action_fix_ids: canonicalRepairs.map((item) => item.fix_id),
      canonical_repairs: canonicalRepairs, recommendations: [...canonicalRepairs].reverse(),
    },
    identity: { scan_id: "scan_v2_grok", project_id: "project_1", normalized_domain: "example.com" },
    userId: "user_1", now: "2026-08-20T20:30:00.000Z",
  });
  const secret = "grok-v2-roundtrip-secret";
  const proof = await createAuthoritySeal(snapshot, secret);
  const rows = durableAuthorityRowsFromSnapshot(snapshot, { fixListId: "fixlist_v2_grok", ownerUserId: "user_1", proof });
  const reconstructed = authoritySnapshotFromRows({
    scan: { id: "scan_v2_grok", project_id: "project_1", ...rows.scanRun },
    fixList: { id: "fixlist_v2_grok", ...rows.fixList },
    fixItems: [...rows.fixItems].reverse(), userId: "user_1",
  });
  assert.deepEqual(reconstructed, snapshot);
  assert.equal(await verifyAuthoritySeal(reconstructed, secret, proof), true);
  assert.deepEqual(reconstructed.recommendations.map((item) => item.action_priority), ["fix_first", "improve"]);
});

test("server review snapshot survives the actual persistence and Grok reconstruction round trip", async () => {
  const now = "2026-08-01T17:20:00.000Z";
  const secret = "round-trip-authority-secret-that-is-never-deployed";
  const snapshot = buildAuthoritySnapshot({
    scan: {
      scanner_version: "python_scanner_v3_bounded_request",
      scanner_build_revision: "authenticated_health_probe_v1",
      scanner_wrapper_version: "runAdvancedScan_v22_python_required",
      advanced_scan_backend: "python_scanner_api",
      deno_fallback_used: false,
      beta_revision_fingerprint: RELEASE_FINGERPRINT,
      metadata_evidence_version: "metadata_v1",
      title_evidence_version: "title_v1",
      submitted_url: "https://www.example.com/",
      website_url: "https://www.example.com/",
      final_url: "https://www.example.com/final",
      pages_found: 9,
      pages_crawled: 7,
    },
    review: {
      archetype_classifier_version: "archetype_classifier_v9_local_business_hospitality",
      review_version: "python_review_v2_structural_marketplace",
      review_evidence_calibration_version: "review_evidence_calibration_v6_health_score_v2",
      ai_review_backend: "python_review_api",
      python_review_fallback_used: false,
      release_gate_eligible: true,
      score_is_provisional: false,
      evidence_quality_blocking: false,
      beta_revision_fingerprint: RELEASE_FINGERPRINT,
      metadata_evidence_version: "metadata_v1",
      title_evidence_version: "title_v1",
      scan_status: "complete",
      health_score: 88,
      health_grade: "Good",
      customer_summary: "Server-grounded summary",
      recommendations: [
        { fix_id: "fix_z", issue_title: "Second by id", priority: "low", affected_pages: ["/z"] },
        {
          fix_id: "fix_a",
          issue_title: "First by id",
          priority: "high",
          affected_pages: ["/a"],
          raw_finding: { verified_urls: [{ url: "https://example.com/a", status_code: 404 }] },
        },
      ],
    },
    identity: { scan_id: "scan_1", project_id: "project_1", normalized_domain: "www.example.com" },
    userId: "user_1",
    now,
  });
  assert.deepEqual(snapshot.recommendations.map((fix) => fix.fix_id), ["fix_a", "fix_z"]);
  assert.equal(snapshot.sealed_at, now);
  assert.equal(snapshot.scan.completed_at, now);
  assert.equal(snapshot.fix_list.generated_at, now);
  assert.equal(snapshot.normalized_domain, "example.com");
  assert.equal(snapshot.scan.website_url, "https://www.example.com/");
  assert.equal(snapshot.fix_list.website_url, "https://www.example.com/");

  const proof = await createAuthoritySeal(snapshot, secret);
  const rows = authorityRowsFromSnapshot(snapshot, {
    fixListId: "fixlist_1",
    ownerUserId: "user_1",
    proof,
  });
  const reconstructed = authoritySnapshotFromRows({
    scan: { id: "scan_1", project_id: "project_1", ...rows.scanRun },
    fixList: { id: "fixlist_1", ...rows.fixList },
    fixItems: [...rows.fixItems].reverse(),
    userId: "user_1",
  });
  assert.deepEqual(reconstructed, snapshot);
  assert.equal(await verifyAuthoritySeal(reconstructed, secret, proof), true);
  const durableRows = durableAuthorityRowsFromSnapshot(snapshot, {
    fixListId: "fixlist_1",
    ownerUserId: "user_1",
    proof,
  });
  assert.equal(durableRows.scanRun.status, "complete");
  assert.equal(durableRows.scanRun.status_detail, "");

  const changedRows = structuredClone(rows);
  changedRows.fixItems[0].recommended_value = "attacker changed this";
  const changed = authoritySnapshotFromRows({
    scan: { id: "scan_1", project_id: "project_1", ...changedRows.scanRun },
    fixList: { id: "fixlist_1", ...changedRows.fixList },
    fixItems: changedRows.fixItems,
    userId: "user_1",
  });
  assert.equal(await verifyAuthoritySeal(changed, secret, proof), false);

  const recovered = missingAuthorityFixRows(rows.fixItems, [rows.fixItems[0]]);
  assert.deepEqual(recovered.map((item) => item.fix_id), [rows.fixItems[1].fix_id]);
});

test("only trusted server worker evidence can enter the active durable authority persistence path", () => {
  assert.match(durableWorkerSource, /invoke_function\(client, "durableScanWorkerControl"/);
  assert.match(durableWorkerSource, /invoke_function\(client, "persistDurableScanAuthority"/);
  assert.match(durablePersistenceSource, /assertWorkerHeader\(req\)/);
  assert.match(durablePersistenceSource, /verifyAuthoritySeal\(signedDocument, secret, proof\)/);
  assert.match(durablePersistenceSource, /buildAuthoritySnapshot\(\{/);
  assert.match(durablePersistenceSource, /entities\.FixList\.create/);
  assert.match(durablePersistenceSource, /entities\.FixItem\.(?:bulkCreate|create)/);
  assert.match(durablePersistenceSource, /entities\.ScanRun\.update/);
  assert.match(durablePersistenceSource, /authority_proof/);
  assert.match(durablePersistenceSource, /releaseAdmission\(\{/);
  const submitStart = scanFormSource.indexOf("async function handleSubmit");
  const submitEnd = scanFormSource.indexOf("\n  return (", submitStart);
  const submitSource = scanFormSource.slice(submitStart, submitEnd);
  assert.match(submitSource, /submitStandardScanJob\(scanPayload\)/);
  assert.doesNotMatch(submitSource, /persistScanAuthority|aiReviewScan|runAdvancedScan|runStandard150Scan/);
  assert.match(functionSource, /await assertServerAuthoritySeal\(\{ scan, fixList, fixItems, user \}\)/);
  assert.match(functionSource, /verifyAuthoritySeal\(snapshot, secret, scan\.authority_proof\)/);
  assert.ok(functionSource.indexOf("await assertServerAuthoritySeal") < functionSource.indexOf("await callScannerChat"));
});

test("browser sends no scan evidence or history and the server loads history itself", () => {
  assert.match(functionSource, /const \{ message, scan_id: scanId, conversation_id: conversationId \} = body/);
  assert.doesNotMatch(functionSource, /body\.(scan|history|context|fixes|recommendations)/);
  assert.match(functionSource, /base44\.entities\.GrokMessage\.filter\(/);
  assert.match(functionSource, /body: JSON\.stringify\(\{ message, scan, history \}\)/);

  assert.match(assistantSource, /const payload = \{ message: content, scan_id: scanRun\.id \}/);
  assert.doesNotMatch(assistantSource, /assistantContext|buildMessageWithContext|base44\.agents/);
  assert.doesNotMatch(assistantSource, /payload\.(scan|history|context)/);
});

test("Cloud Run chat uses only server secrets, a bounded timeout, and safe errors", () => {
  assert.match(functionSource, /Deno\.env\.get\("GROK_CHAT_ENABLED"\) !== "true"/);
  assert.match(functionSource, /"grok_disabled"/);
  assert.match(functionSource, /Deno\.env\.get\("SCANNER_API_URL"\)/);
  assert.match(functionSource, /Deno\.env\.get\("SCANNER_API_KEY"\)/);
  assert.match(functionSource, /`\$\{scannerApiUrl\}\/chat`/);
  assert.match(functionSource, /"X-Scanner-Key": scannerApiKey/);
  assert.match(functionSource, /const CHAT_TIMEOUT_MS = 95_000/);
  assert.match(functionSource, /new AbortController\(\)/);
  assert.match(functionSource, /SAFE_UNAVAILABLE_MESSAGE/);
  assert.doesNotMatch(functionSource, /error\?\.message|String\(error\)/);
});

test("Grok is disabled and absent from the customer application", () => {
  assert.match(appSource, /path="\/assistant"[\s\S]*<Navigate to="\/dashboard" replace \/>/);
  assert.doesNotMatch(appSource, /import Assistant/);
  assert.doesNotMatch(appSource, /<Assistant \/>/);
  assert.doesNotMatch(layoutSource, /Ask Grok|\/assistant/);
});

test("the latest authoritative scan must belong to the active project and domain", () => {
  const selected = selectLatestAuthoritativeGrokScan([
    { ...scan, id: "limited", status: "limited", completed_at: "2026-08-03T10:00:00Z" },
    { ...scan, id: "wrong-domain", website_url: "https://other.example", completed_at: "2026-08-02T10:00:00Z" },
    { ...scan, id: "older", completed_at: "2026-07-31T10:00:00Z" },
    scan,
  ], { id: "project_1", owner_user_id: "owner_1", website_url: "https://example.com" });

  assert.equal(selected.id, "scan_current");
  assert.equal(normalizeGrokDomain("HTTPS://WWW.Example.com./a"), "example.com");
  assert.equal(normalizeGrokDomain("javascript:alert(1)"), "");
});

test("conversation selection rejects cross-scan, cross-domain, and stale-release records", () => {
  assert.equal(conversationMatchesGrokScan(conversation, scan), true);
  assert.equal(conversationMatchesGrokScan({ ...conversation, scan_run_id: "scan_other" }, scan), false);
  assert.equal(conversationMatchesGrokScan({ ...conversation, normalized_domain: "other.example" }, scan), false);
  assert.equal(conversationMatchesGrokScan({ ...conversation, release_fingerprint: "release_old" }, scan), false);

  const latest = selectGrokConversationForScan([
    { ...conversation, id: "older", last_message_at: "2026-07-30T11:00:00Z" },
    { ...conversation, id: "wrong", scan_run_id: "scan_other", last_message_at: "2026-08-02T11:00:00Z" },
    conversation,
  ], scan);
  assert.equal(latest.id, "conversation_current");
});

test("failed sends preserve the current matching conversation but never stale domain state", () => {
  assert.equal(resolveActiveGrokConversationId({
    currentConversation: conversation,
    candidateConversation: null,
    scanRun: scan,
  }), conversation.id);

  assert.equal(resolveActiveGrokConversationId({
    currentConversation: { ...conversation, normalized_domain: "other.example" },
    candidateConversation: null,
    scanRun: scan,
  }), null);
  assert.match(assistantSource, /resolveActiveGrokConversationId\(\{/);
  assert.match(assistantSource, /Your current FixList conversation was not switched/);
});

test("the send guard rejects duplicate in-flight sends and unlocks after completion", () => {
  const guard = createGrokSendGuard();
  assert.equal(guard.tryAcquire(), true);
  assert.equal(guard.tryAcquire(), false);
  assert.equal(guard.isLocked(), true);
  guard.release();
  assert.equal(guard.tryAcquire(), true);
  assert.match(assistantSource, /sendGuardRef\.current\.tryAcquire\(\)/);
  assert.match(assistantSource, /sendGuardRef\.current\.release\(\)/);
});

test("late Grok responses are rejected across owner, project, scan, domain, and release changes", () => {
  const current = grokWorkspaceIdentity({ scanRun: scan });
  assert.equal(grokWorkspaceMatches(current, current), true);
  for (const mismatch of [
    { ...scan, owner_user_id: "owner_2" },
    { ...scan, project_id: "project_2" },
    { ...scan, id: "scan_2" },
    { ...scan, website_url: "https://other.example" },
    { ...scan, beta_revision_fingerprint: "release_2" },
  ]) assert.equal(grokWorkspaceMatches(current, grokWorkspaceIdentity({ scanRun: mismatch })), false);
  assert.match(assistantSource, /assertCurrentGrokWorkspace\(workspaceAtSend, workspaceIdentityRef\.current\)/);
  assert.match(assistantSource, /CUSTOMER_BOUNDARY_EVENT/);
});

test("refresh persistence loads entity conversations and ordered messages", () => {
  assert.match(assistantSource, /base44\.entities\.GrokConversation\.filter\(/);
  assert.match(assistantSource, /base44\.entities\.GrokMessage\.filter\(/);
  assert.match(assistantSource, /base44\.entities\.ScanRun\.subscribe\(/);
  assert.deepEqual(sortGrokMessages([
    { id: "two", sequence: 2, created_date: "2026-08-01T10:01:00Z" },
    { id: "one", sequence: 1, created_date: "2026-08-01T10:00:00Z" },
  ]).map((item) => item.id), ["one", "two"]);
});

test("Assistant is explicitly Grok in FixList and never claims it applied changes", () => {
  assert.match(assistantSource, /Grok in FixList/);
  assert.match(assistantSource, /it never changes your website or marks fixes complete/);
  assert.match(assistantSource, /Advice only — Grok cannot apply fixes/);
  assert.doesNotMatch(assistantSource, /fixes were applied|changes were published|I fixed/i);
});
