import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  createAuthoritySeal,
  verifyAuthoritySeal,
} from "../../base44/functions/grokChat/authoritySeal.js";
import { buildAuthoritySnapshot } from "../../base44/functions/aiReviewScan/authoritySnapshot.js";
import {
  authorityRowsFromSnapshot,
  missingAuthorityFixRows,
} from "../../base44/functions/persistScanAuthority/authorityRows.js";
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
      beta_revision_fingerprint: "51c813a6219b4e70",
      metadata_evidence_version: "metadata_v1",
      title_evidence_version: "title_v1",
      final_url: "https://www.example.com/final",
      pages_found: 9,
      pages_crawled: 7,
    },
    review: {
      archetype_classifier_version: "archetype_classifier_v9_local_business_hospitality",
      review_version: "python_review_v2_structural_marketplace",
      review_evidence_calibration_version: "review_evidence_calibration_v5_utility_redirect",
      ai_review_backend: "python_review_api",
      python_review_fallback_used: false,
      release_gate_eligible: true,
      score_is_provisional: false,
      evidence_quality_blocking: false,
      beta_revision_fingerprint: "51c813a6219b4e70",
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

test("only trusted server scan and review results can enter the authority persistence path", () => {
  assert.match(scannerFunctionSource, /const result = toPythonAdvancedScanResponse/);
  assert.match(scannerFunctionSource, /attachScanAttestation\(\{ base44, user, result, websiteUrl \}\)/);
  assert.match(scannerFunctionSource, /base44\.entities\.ScanRun\.get\(scanId\)/);
  assert.match(scannerFunctionSource, /createAuthoritySeal\(document, secret\)/);

  assert.match(reviewFunctionSource, /resolveTrustedScan\(\{ base44, user, requestBody \}\)/);
  assert.match(reviewFunctionSource, /verifyAuthoritySeal\(document, secret, attestation\.proof\)/);
  assert.match(reviewFunctionSource, /mergeTrustedScanWithClientContext\(trustedScan\.result/);
  assert.match(reviewFunctionSource, /buildAuthoritySnapshot\(\{[\s\S]*scan: trustedScan\.result,[\s\S]*review: result/);

  assert.match(persistenceFunctionSource, /verifyAuthoritySeal\(attestation\.snapshot, secret, attestation\.proof\)/);
  assert.match(persistenceFunctionSource, /createServiceOnlyClient\(req\)/);
  assert.match(persistenceFunctionSource, /Base44-Service-Authorization/);
  assert.match(persistenceFunctionSource, /serviceToken: serviceAuthorization\.slice/);
  assert.match(persistenceFunctionSource, /serviceEntities\.FixList\.create/);
  assert.match(persistenceFunctionSource, /serviceEntities\.FixItem\.bulkCreate/);
  assert.match(persistenceFunctionSource, /serviceEntities\.ScanRun\.update/);
  assert.doesNotMatch(persistenceFunctionSource, /base44\.asServiceRole\.entities/);
  assert.match(persistenceFunctionSource, /authority_proof: String\(attestation\.proof\)\.toLowerCase\(\)/);
  assert.match(persistenceFunctionSource, /missingAuthorityFixRows\(rows\.fixItems, existingItems\)/);
  assert.match(persistenceFunctionSource, /const persistedScan = await serviceEntities\.ScanRun\.get\(scanId\)/);
  assert.match(persistenceFunctionSource, /const persistedFixList = await serviceEntities\.FixList\.get\(fixList\.id\)/);
  assert.match(persistenceFunctionSource, /authority_persistence_incomplete/);
  assert.match(persistenceFunctionSource, /persistedItems\.length === snapshot\.recommendations\.length/);
  assert.doesNotMatch(persistenceFunctionSource, /createAuthoritySeal/);

  assert.match(scanFormSource, /authoritative_scan: \{/);
  assert.match(scanFormSource, /authority_review_payload: scanData\.authority_review_payload/);
  assert.match(scanFormSource, /authority_scan_attestation: scanData\.authority_scan_attestation/);
  assert.doesNotMatch(scanFormSource, /authoritative_scan: scanData,/);
  assert.match(scanFormSource, /"persistScanAuthority"/);
  assert.match(scanFormSource, /scan_authority_persistence_failed/);
  assert.match(scanFormSource, /scan_authority_attestation_missing/);
  assert.match(scanFormSource, /aiData\?\.release_gate_eligible === true && !usingAuthorityPersistence/);
  assert.match(scanFormSource, /release_gate_eligible: false, is_authoritative: false/);
  assert.match(scanFormSource, /\^\[a-f0-9\]\{64\}\$/);
  assert.match(scanFormSource, /completion\.scanRun\.authority_seal_version/);
  assert.match(scanFormSource, /completion\.scanRun\.authority_sealed_at/);
  assert.match(scanFormSource, /completion\.scanRun\.release_gate_eligible === true/);
  assert.match(scanFormSource, /Boolean\(completion\.fixListId\)/);
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

test("Grok is reachable only inside the authenticated customer app", () => {
  assert.match(appSource, /<ProtectedRoute[\s\S]*path="\/assistant" element=\{<Assistant \/>\}/);
  assert.match(layoutSource, /\{ name: "Ask Grok", href: "\/assistant" \}/);
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
