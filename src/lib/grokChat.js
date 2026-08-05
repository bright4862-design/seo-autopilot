export const GROK_MAX_MESSAGE_LENGTH = 2_000;

export function normalizeGrokDomain(value) {
  const raw = typeof value === "string" ? value.trim() : "";
  if (!raw) return "";
  try {
    const parsed = new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`);
    if (!["http:", "https:"].includes(parsed.protocol)) return "";
    return parsed.hostname.toLowerCase().replace(/^www\./, "").replace(/\.$/, "");
  } catch {
    return "";
  }
}

export function isAuthoritativeGrokScan(scanRun = {}) {
  return scanRun.status === "complete"
    && scanRun.release_gate_eligible === true
    && scanRun.score_is_provisional !== true
    && scanRun.evidence_quality_blocking !== true
    && Boolean(normalizeGrokDomain(scanRun.website_url))
    && Boolean(String(scanRun.beta_revision_fingerprint || "").trim());
}

export function selectLatestAuthoritativeGrokScan(scanRuns = [], project = {}) {
  const projectId = String(project?.id || "");
  const projectDomain = normalizeGrokDomain(project?.website_url);
  const projectOwner = String(project?.owner_user_id || project?.created_by_id || "");
  return [...(Array.isArray(scanRuns) ? scanRuns : [])]
    .filter((run) => (
      isAuthoritativeGrokScan(run)
      && Boolean(projectOwner)
      && String(run.owner_user_id || "") === projectOwner
      && String(run.project_id || "") === projectId
      && normalizeGrokDomain(run.website_url) === projectDomain
    ))
    .sort((left, right) => recordTime(right) - recordTime(left))[0] || null;
}

export function conversationMatchesGrokScan(conversation = {}, scanRun = {}) {
  const expectedOwner = String(scanRun.owner_user_id || "");
  return Boolean(conversation?.id && scanRun?.id && expectedOwner)
    && String(conversation.owner_user_id || "") === expectedOwner
    && String(conversation.project_id || "") === String(scanRun.project_id || "")
    && String(conversation.scan_run_id || "") === String(scanRun.id || "")
    && normalizeGrokDomain(conversation.normalized_domain) === normalizeGrokDomain(scanRun.website_url)
    && String(conversation.release_fingerprint || "")
      === String(scanRun.beta_revision_fingerprint || "");
}


export function grokWorkspaceIdentity(input = {}) {
  const scanRun = input.scanRun || input;
  return {
    owner_id: String(input.ownerId || input.owner_id || scanRun?.owner_user_id || ""),
    project_id: String(input.projectId || input.project_id || scanRun?.project_id || ""),
    scan_id: String(input.scanId || input.scan_id || scanRun?.id || ""),
    normalized_domain: normalizeGrokDomain(
      input.normalizedDomain || input.normalized_domain || scanRun?.website_url,
    ),
    release_identity: String(
      input.releaseIdentity || input.release_identity || scanRun?.beta_revision_fingerprint || "",
    ),
  };
}

export function grokWorkspaceMatches(left, right) {
  const a = grokWorkspaceIdentity(left || {});
  const b = grokWorkspaceIdentity(right || {});
  return ["owner_id", "project_id", "scan_id", "normalized_domain", "release_identity"]
    .every((field) => Boolean(a[field]) && a[field] === b[field]);
}

export function selectGrokConversationForScan(conversations = [], scanRun = {}) {
  return [...(Array.isArray(conversations) ? conversations : [])]
    .filter((conversation) => conversationMatchesGrokScan(conversation, scanRun))
    .sort((left, right) => recordTime(right, "last_message_at") - recordTime(left, "last_message_at"))[0] || null;
}

export function resolveActiveGrokConversationId({ currentConversation, candidateConversation, scanRun } = {}) {
  if (conversationMatchesGrokScan(candidateConversation, scanRun)) return candidateConversation.id;
  if (conversationMatchesGrokScan(currentConversation, scanRun)) return currentConversation.id;
  return null;
}

export function sortGrokMessages(messages = []) {
  return [...(Array.isArray(messages) ? messages : [])].sort((left, right) => {
    const sequenceDifference = Number(left.sequence || 0) - Number(right.sequence || 0);
    if (sequenceDifference) return sequenceDifference;
    return recordTime(left) - recordTime(right);
  });
}

export function createGrokSendGuard() {
  let locked = false;
  return {
    tryAcquire() {
      if (locked) return false;
      locked = true;
      return true;
    },
    release() {
      locked = false;
    },
    reset() {
      locked = false;
    },
    isLocked() {
      return locked;
    },
  };
}

function recordTime(record = {}, preferredField = "completed_at") {
  const value = record?.[preferredField]
    || record?.updated_date
    || record?.created_date
    || record?.created_at
    || "";
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? timestamp : 0;
}
