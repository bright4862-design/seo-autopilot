import { createClientFromRequest } from "npm:@base44/sdk";
import { verifyAuthoritySeal } from "./authoritySeal.js";
import { authoritySnapshotFromRows } from "./authoritySnapshot.js";

const MAX_MESSAGE_LENGTH = 2_000;
const MAX_ID_LENGTH = 160;
const MAX_HISTORY_MESSAGES = 20;
const MAX_FIX_ITEMS = 100;
const CHAT_TIMEOUT_MS = 95_000;
const REVIEW_ATTESTATION_VERSION = "standard_review_snapshot_hmac_v1";
const EXPECTED_RELEASE_FINGERPRINT = "51c813a6219b4e70";
const SAFE_UNAVAILABLE_MESSAGE = "Grok is temporarily unavailable. Your FixList conversation is still saved; please try again.";

class RequestProblem extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

Deno.serve(async (req) => {
  if (req.method !== "POST") {
    return errorResponse(405, "method_not_allowed", "Use POST to send a Grok message.");
  }

  const base44 = createClientFromRequest(req);
  let user: any;
  try {
    user = await base44.auth.me();
  } catch {
    return errorResponse(401, "unauthorized", "Sign in to use Grok in FixList.");
  }
  if (!user?.id) {
    return errorResponse(401, "unauthorized", "Sign in to use Grok in FixList.");
  }

  // Default-off rollout switch. This is enforced server-side so hiding the UI
  // can never enable an unapproved beta integration.
  if (Deno.env.get("GROK_CHAT_ENABLED") !== "true") {
    return errorResponse(503, "grok_disabled", "Grok is not enabled for this FixList workspace yet.");
  }

  const body = await readJsonObject(req);
  const { message, scan_id: scanId, conversation_id: conversationId } = body;

  let cleanMessage: string;
  let cleanScanId: string;
  let cleanConversationId: string;
  try {
    cleanMessage = requireMessage(message);
    cleanScanId = requireId(scanId, "scan_id");
    cleanConversationId = optionalId(conversationId, "conversation_id");
  } catch (error) {
    return problemResponse(error);
  }

  try {
    // These reads deliberately use the caller-scoped client. Base44 RLS is the
    // first authorization boundary; the explicit checks below are the second.
    const scan = await getUserRecord(
      base44.entities.ScanRun,
      cleanScanId,
      new RequestProblem(404, "scan_not_found", "An authoritative scan was not found.")
    );
    assertOwnedBy(scan, user, "scan_not_found", "An authoritative scan was not found.");

    const fixList = await loadFixList(base44, scan, user);
    const fixItems = await loadFixItems(base44, fixList, scan, user);
    const authoritySnapshot = await assertServerAuthoritySeal({ scan, fixList, fixItems, user });
    assertAuthoritativeScan(authoritySnapshot.scan);

    const domain = normalizeDomain(authoritySnapshot.normalized_domain);
    const projectId = cleanId(authoritySnapshot.project_id);
    const releaseFingerprint = cleanText(authoritySnapshot.release_fingerprint, MAX_ID_LENGTH);
    if (!domain || !projectId || !releaseFingerprint) {
      throw new RequestProblem(409, "scan_identity_incomplete", "The selected scan is missing release identity data.");
    }

    const project = await getUserRecord(
      base44.entities.BusinessProject,
      projectId,
      new RequestProblem(404, "project_not_found", "The scan project was not found.")
    );
    assertOwnedBy(project, user, "project_not_found", "The scan project was not found.");
    if (cleanId(project.id) !== projectId || normalizeDomain(project.website_url) !== domain) {
      throw new RequestProblem(409, "project_domain_mismatch", "The selected scan no longer matches this project domain.");
    }

    const scannerApiUrl = cleanText(Deno.env.get("SCANNER_API_URL"), 2_000).replace(/\/+$/, "");
    const scannerApiKey = cleanText(Deno.env.get("SCANNER_API_KEY"), 2_000);
    if (!scannerApiUrl || !scannerApiKey) {
      return errorResponse(503, "grok_not_configured", "Grok is not available for this FixList workspace yet.");
    }

    let conversation: any;
    if (cleanConversationId) {
      conversation = await getUserRecord(
        base44.entities.GrokConversation,
        cleanConversationId,
        new RequestProblem(404, "conversation_not_found", "This Grok conversation was not found.")
      );
      assertOwnedBy(conversation, user, "conversation_not_found", "This Grok conversation was not found.");
      assertConversationIdentity(conversation, {
        projectId,
        scanId: cleanScanId,
        domain,
        releaseFingerprint,
      });
    } else {
      conversation = await base44.asServiceRole.entities.GrokConversation.create({
        owner_user_id: user.id,
        project_id: projectId,
        scan_run_id: cleanScanId,
        normalized_domain: domain,
        release_fingerprint: releaseFingerprint,
        title: `${domain} Grok help`.slice(0, 120),
        status: "active",
        last_message_at: new Date().toISOString(),
        message_count: 0,
        model: "",
        grok_chat_version: "",
      });
    }

    const historyRecords = await loadConversationHistory(base44, conversation, user, {
      projectId,
      scanId: cleanScanId,
      domain,
      releaseFingerprint,
    });
    const nextSequence = historyRecords.reduce(
      (maximum: number, item: any) => Math.max(maximum, Number(item.sequence || 0)),
      0
    ) + 1;

    const messageIdentity = {
      owner_user_id: user.id,
      conversation_id: conversation.id,
      project_id: projectId,
      scan_run_id: cleanScanId,
      normalized_domain: domain,
      release_fingerprint: releaseFingerprint,
    };
    const userMessage = await base44.asServiceRole.entities.GrokMessage.create({
      ...messageIdentity,
      role: "user",
      content: cleanMessage,
      sequence: nextSequence,
      model: "",
      grok_chat_version: "",
    });

    const upstream = await callScannerChat({
      scannerApiUrl,
      scannerApiKey,
      message: cleanMessage,
      scan: buildScanEvidence({
        project,
        scan: authoritySnapshot.scan,
        fixList: authoritySnapshot.fix_list,
        fixItems: authoritySnapshot.recommendations,
        domain,
      }),
      history: historyRecords.map((item: any) => ({
        role: item.role,
        content: cleanText(item.content, 2_000),
      })),
    });

    if (!upstream.success) {
      await safeConversationUpdate(base44, conversation.id, {
        last_message_at: new Date().toISOString(),
        message_count: nextSequence,
      });
      return Response.json({
        success: false,
        error_code: "grok_unavailable",
        error: SAFE_UNAVAILABLE_MESSAGE,
        conversation_id: safeId(conversation.id),
        user_message_id: safeId(userMessage.id),
        assistant_message_id: "",
        scan_id: cleanScanId,
        model: "",
        grok_chat_version: "",
      });
    }

    const assistantMessage = await base44.asServiceRole.entities.GrokMessage.create({
      ...messageIdentity,
      role: "assistant",
      content: upstream.answer,
      sequence: nextSequence + 1,
      model: upstream.model,
      grok_chat_version: upstream.version,
    });
    await safeConversationUpdate(base44, conversation.id, {
      last_message_at: new Date().toISOString(),
      message_count: nextSequence + 1,
      model: upstream.model,
      grok_chat_version: upstream.version,
    });

    return Response.json({
      success: true,
      error_code: "",
      error: "",
      conversation_id: safeId(conversation.id),
      user_message_id: safeId(userMessage.id),
      assistant_message_id: safeId(assistantMessage.id),
      scan_id: cleanScanId,
      model: upstream.model,
      grok_chat_version: upstream.version,
    });
  } catch (error) {
    if (error instanceof RequestProblem) return problemResponse(error);
    console.error("grokChat failed", error instanceof Error ? error.name : "unknown_error");
    return errorResponse(500, "grok_chat_failed", "Grok could not process this request. Your FixList was not changed.");
  }
});

async function loadFixList(base44: any, scan: any, user: any) {
  let fixList: any = null;
  try {
    if (scan.fix_list_id) {
      fixList = await base44.entities.FixList.get(scan.fix_list_id);
    } else {
      const matches = await base44.entities.FixList.filter(
        {
          scan_run_id: scan.id,
          project_id: scan.project_id,
          owner_user_id: user.id,
        },
        "-generated_at",
        1
      );
      fixList = matches?.[0] || null;
    }
  } catch {
    throw new RequestProblem(409, "fix_list_unavailable", "The authoritative FixList for this scan is unavailable.");
  }

  if (!fixList) {
    throw new RequestProblem(409, "fix_list_unavailable", "The authoritative FixList for this scan is unavailable.");
  }
  assertOwnedBy(fixList, user, "fix_list_unavailable", "The authoritative FixList for this scan is unavailable.");
  if (
    cleanId(fixList.scan_run_id) !== cleanId(scan.id)
    || cleanId(fixList.project_id) !== cleanId(scan.project_id)
    || cleanText(fixList.authority_proof, 64) !== cleanText(scan.authority_proof, 64)
    || fixList.is_authoritative !== true
    || normalizeDomain(fixList.website_url) !== normalizeDomain(scan.website_url)
  ) {
    throw new RequestProblem(409, "fix_list_mismatch", "The FixList does not match the selected authoritative scan.");
  }
  return fixList;
}

async function loadFixItems(base44: any, fixList: any, scan: any, user: any) {
  let items: any[];
  try {
    items = await base44.entities.FixItem.filter(
      {
        fix_list_id: fixList.id,
        scan_run_id: scan.id,
        project_id: scan.project_id,
        owner_user_id: user.id,
        authority_proof: scan.authority_proof,
      },
      "-created_date",
      MAX_FIX_ITEMS
    );
  } catch {
    throw new RequestProblem(409, "fix_items_unavailable", "The recommendations for this FixList are unavailable.");
  }

  for (const item of items || []) {
    assertOwnedBy(item, user, "fix_items_mismatch", "The recommendations do not match this FixList.");
    if (
      cleanId(item.fix_list_id) !== cleanId(fixList.id)
      || cleanId(item.scan_run_id) !== cleanId(scan.id)
      || cleanId(item.project_id) !== cleanId(scan.project_id)
    ) {
      throw new RequestProblem(409, "fix_items_mismatch", "The recommendations do not match this FixList.");
    }
  }
  return items || [];
}

async function loadConversationHistory(base44: any, conversation: any, user: any, identity: any) {
  let newest: any[];
  try {
    newest = await base44.entities.GrokMessage.filter(
      {
        conversation_id: conversation.id,
        owner_user_id: user.id,
        project_id: identity.projectId,
        scan_run_id: identity.scanId,
        normalized_domain: identity.domain,
        release_fingerprint: identity.releaseFingerprint,
      },
      "-created_date",
      MAX_HISTORY_MESSAGES
    );
  } catch {
    throw new RequestProblem(409, "history_unavailable", "This Grok conversation history is unavailable.");
  }

  for (const item of newest || []) {
    assertOwnedBy(item, user, "history_mismatch", "This Grok conversation does not match the selected scan.");
    assertMessageIdentity(item, conversation.id, identity);
  }
  return (newest || [])
    .filter((item) => ["user", "assistant"].includes(item.role) && cleanText(item.content, 2_000))
    .reverse();
}

async function assertServerAuthoritySeal({ scan, fixList, fixItems, user }: any) {
  if (
    cleanText(scan.authority_seal_version, MAX_ID_LENGTH) !== REVIEW_ATTESTATION_VERSION
    || !cleanText(scan.authority_sealed_at, 80)
    || !/^[a-f0-9]{64}$/.test(cleanText(scan.authority_proof, 64))
  ) {
    throw new RequestProblem(409, "evidence_not_server_authoritative", "Grok requires evidence persisted by the server authority pipeline.");
  }
  const secret = cleanText(Deno.env.get("SCAN_EVIDENCE_SIGNING_KEY"), 4_000);
  if (!secret) {
    throw new RequestProblem(503, "evidence_authority_not_configured", "Server evidence authority is not configured.");
  }

  const snapshot = authoritySnapshotFromRows({ scan, fixList, fixItems, userId: user.id });
  if (
    snapshot.version !== REVIEW_ATTESTATION_VERSION
    || snapshot.release_fingerprint !== EXPECTED_RELEASE_FINGERPRINT
    || cleanId(snapshot.owner_user_id) !== cleanId(user.id)
    || cleanId(snapshot.scan_id) !== cleanId(scan.id)
    || !await verifyAuthoritySeal(snapshot, secret, scan.authority_proof)
  ) {
    throw new RequestProblem(409, "evidence_authority_invalid", "The saved FixList evidence no longer matches its server authority seal.");
  }
  return snapshot;
}

function assertAuthoritativeScan(scan: any) {
  if (
    scan.status !== "complete"
    || scan.release_gate_eligible !== true
    || scan.score_is_provisional === true
    || scan.evidence_quality_blocking === true
  ) {
    throw new RequestProblem(409, "scan_not_authoritative", "Grok requires a completed authoritative FixList scan.");
  }
}

function assertOwnedBy(record: any, user: any, code: string, message: string) {
  const ownerMatches = cleanId(record?.owner_user_id) === cleanId(user?.id);
  const creatorIdMatches = cleanId(record?.created_by_id) === cleanId(user?.id);
  const creatorEmailMatches = cleanText(record?.created_by, 320).toLowerCase()
    === cleanText(user?.email, 320).toLowerCase();
  if (!ownerMatches && !creatorIdMatches && !creatorEmailMatches) {
    throw new RequestProblem(404, code, message);
  }
}

function assertConversationIdentity(conversation: any, identity: any) {
  if (
    conversation.status !== "active"
    || cleanId(conversation.project_id) !== identity.projectId
    || cleanId(conversation.scan_run_id) !== identity.scanId
    || cleanText(conversation.normalized_domain, 253) !== identity.domain
    || cleanText(conversation.release_fingerprint, MAX_ID_LENGTH) !== identity.releaseFingerprint
  ) {
    throw new RequestProblem(409, "conversation_scan_mismatch", "This Grok conversation belongs to a different scan. Start a new chat.");
  }
}

function assertMessageIdentity(message: any, conversationId: string, identity: any) {
  if (
    cleanId(message.conversation_id) !== cleanId(conversationId)
    || cleanId(message.project_id) !== identity.projectId
    || cleanId(message.scan_run_id) !== identity.scanId
    || cleanText(message.normalized_domain, 253) !== identity.domain
    || cleanText(message.release_fingerprint, MAX_ID_LENGTH) !== identity.releaseFingerprint
  ) {
    throw new RequestProblem(409, "history_mismatch", "This Grok conversation does not match the selected scan.");
  }
}

function buildScanEvidence({ project, scan, fixList, fixItems, domain }: any) {
  return {
    release_gate_eligible: true,
    scan_id: safeId(scan.id),
    project_id: safeId(project.id),
    website_url: cleanText(scan.website_url, 2_000),
    normalized_domain: domain,
    beta_revision_fingerprint: cleanText(scan.beta_revision_fingerprint, MAX_ID_LENGTH),
    scanner_version: cleanText(scan.scanner_version, MAX_ID_LENGTH),
    scanner_build_revision: cleanText(scan.scanner_build_revision, MAX_ID_LENGTH),
    review_version: cleanText(scan.review_version, MAX_ID_LENGTH),
    scan_status: cleanText(scan.scan_status || scan.status, 120),
    health_score: finiteNumber(scan.health_score),
    health_grade: cleanText(scan.health_grade, 40),
    pages_found: finiteNumber(scan.pages_found),
    pages_crawled: finiteNumber(scan.pages_crawled),
    customer_summary: cleanText(scan.customer_summary, 4_000),
    next_best_step: cleanText(scan.next_best_step, 2_000),
    project: {
      business_name: cleanText(project.business_name, 300),
      website_url: cleanText(project.website_url, 2_000),
      business_type: cleanText(project.business_type, 200),
      cms_platform: cleanText(project.cms_platform, 120),
    },
    fix_list: {
      id: safeId(fixList.id),
      total_fixes: finiteNumber(fixList.total_fixes),
      critical_count: finiteNumber(fixList.critical_count),
      high_count: finiteNumber(fixList.high_count),
      medium_count: finiteNumber(fixList.medium_count),
      low_count: finiteNumber(fixList.low_count),
      completed_count: finiteNumber(fixList.completed_count),
      no_high_confidence_findings: fixList.no_high_confidence_findings === true,
    },
    recommendations: (fixItems || []).slice(0, MAX_FIX_ITEMS).map(compactFixItem),
  };
}

function compactFixItem(item: any) {
  const raw = item?.raw_finding && typeof item.raw_finding === "object" ? item.raw_finding : {};
  return {
    fix_id: cleanText(item.fix_id, MAX_ID_LENGTH),
    rule: cleanText(item.rule, 200),
    category: cleanText(item.customer_category || item.category, 200),
    issue_title: cleanText(item.issue_title, 500),
    plain_english_explanation: cleanText(item.plain_english_explanation, 2_000),
    why_it_matters: cleanText(item.why_it_matters, 2_000),
    current_value: cleanText(item.current_value, 2_000),
    recommended_value: cleanText(item.recommended_value, 2_000),
    simple_next_step: cleanText(item.simple_next_step, 2_000),
    priority: cleanText(item.priority, 40),
    difficulty: cleanText(item.difficulty, 120),
    requires_developer: item.requires_developer === true,
    requires_approval: item.requires_approval === true,
    user_status: cleanText(item.user_status, 80),
    page_url: cleanText(item.page_url, 2_000),
    affected_pages: cleanStringArray(item.affected_pages, 25, 2_000),
    source_pages: cleanStringArray(item.source_pages, 25, 2_000),
    what_to_do_steps: cleanStringArray(item.what_to_do_steps, 12, 1_000),
    verified_urls: cleanVerifiedUrls(raw.verified_urls || raw.url_evidence),
  };
}

function cleanVerifiedUrls(value: any) {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 25).map((item: any) => {
    if (typeof item === "string") return { url: cleanText(item, 2_000) };
    return {
      url: cleanText(item?.url, 2_000),
      final_url: cleanText(item?.final_url, 2_000),
      status_code: finiteNumber(item?.status_code),
      verification_state: cleanText(item?.verification_state, 120),
    };
  }).filter((item: any) => item.url || item.final_url);
}

async function callScannerChat({ scannerApiUrl, scannerApiKey, message, scan, history }: any) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), CHAT_TIMEOUT_MS);
  try {
    const response = await fetch(`${scannerApiUrl}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Scanner-Key": scannerApiKey,
      },
      body: JSON.stringify({ message, scan, history }),
      signal: controller.signal,
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok || !payload || payload.success !== true) {
      console.warn("grokChat scanner proxy rejected request", response.status);
      return { success: false };
    }

    const answer = cleanText(payload.answer, 12_000);
    if (!answer) return { success: false };
    return {
      success: true,
      answer,
      model: cleanText(payload.model, 160),
      version: cleanText(payload.grok_chat_version, 160),
    };
  } catch (error) {
    console.warn("grokChat scanner proxy unavailable", error instanceof DOMException ? error.name : "request_failed");
    return { success: false };
  } finally {
    clearTimeout(timeout);
  }
}

async function safeConversationUpdate(base44: any, conversationId: string, data: any) {
  try {
    await base44.asServiceRole.entities.GrokConversation.update(conversationId, data);
  } catch {
    console.warn("grokChat could not update conversation metadata");
  }
}

async function getUserRecord(handler: any, id: string, problem: RequestProblem) {
  try {
    const record = await handler.get(id);
    if (!record) throw problem;
    return record;
  } catch {
    throw problem;
  }
}

async function readJsonObject(req: Request) {
  try {
    const value = await req.json();
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
  } catch {
    return {};
  }
}

function requireMessage(value: any) {
  const message = typeof value === "string" ? value.trim() : "";
  if (!message) throw new RequestProblem(400, "message_required", "Enter a question for Grok.");
  if (message.length > MAX_MESSAGE_LENGTH) {
    throw new RequestProblem(400, "message_too_long", `Keep your question under ${MAX_MESSAGE_LENGTH} characters.`);
  }
  return message;
}

function requireId(value: any, field: string) {
  const id = optionalId(value, field);
  if (!id) throw new RequestProblem(400, `${field}_required`, `${field} is required.`);
  return id;
}

function optionalId(value: any, field: string) {
  const id = typeof value === "string" ? value.trim() : "";
  if (id.length > MAX_ID_LENGTH || /[\u0000-\u001f\u007f]/.test(id)) {
    throw new RequestProblem(400, `${field}_invalid`, `${field} is invalid.`);
  }
  return id;
}

function normalizeDomain(value: any) {
  const raw = cleanText(value, 2_000);
  if (!raw) return "";
  try {
    const parsed = new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`);
    if (!["http:", "https:"].includes(parsed.protocol)) return "";
    return parsed.hostname.toLowerCase().replace(/^www\./, "").replace(/\.$/, "");
  } catch {
    return "";
  }
}

function cleanText(value: any, limit: number) {
  return typeof value === "string" ? value.trim().slice(0, limit) : "";
}

function cleanId(value: any) {
  return cleanText(value, MAX_ID_LENGTH);
}

function safeId(value: any) {
  return cleanId(value);
}

function finiteNumber(value: any) {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

function cleanStringArray(value: any, length: number, itemLength: number) {
  return Array.isArray(value)
    ? value.slice(0, length).map((item) => cleanText(item, itemLength)).filter(Boolean)
    : [];
}

function problemResponse(error: any) {
  if (error instanceof RequestProblem) return errorResponse(error.status, error.code, error.message);
  return errorResponse(400, "invalid_request", "The Grok request is invalid.");
}

function errorResponse(status: number, errorCode: string, message: string) {
  return Response.json({
    success: false,
    error_code: errorCode,
    error: message,
    conversation_id: "",
    user_message_id: "",
    assistant_message_id: "",
    scan_id: "",
    model: "",
    grok_chat_version: "",
  }, { status });
}
