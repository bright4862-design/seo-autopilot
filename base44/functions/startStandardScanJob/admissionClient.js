// Base44 -> Cloud Run client for the Firestore admission coordinator.
//
// Base44 cannot talk to Firestore directly: its functions have no Google
// Application Default Credentials, and constraints/iam.disableServiceAccountKey-
// Creation forbids minting a key to give them any. So this client signs a
// request with the shared signing root and lets the Cloud Run coordinator do
// the privileged work under its own identity -- the same keyless shape the
// Cloud Tasks dispatch gateway already uses.
//
// The signing label differs from the dispatch gateway's on purpose. A
// signature minted for one service must never authenticate against the other.
//
// NOTHING in this module is wired into startStandardScanJob yet. It is gated
// behind BETA_SCAN_ADMISSION_ENABLED, which stays false until the coordinator
// is deployed and the browser path is retired.

export const ADMISSION_LABEL = "fixlist-admission-coordinator-v1";
export const ADMISSION_CLAIM_EVIDENCE_LABEL = "fixlist-admission-claim-evidence-v1";
export const ADMISSION_CLAIM_EVIDENCE_VERSION = "admission_claim_evidence_v1";
export const ADMISSION_FLAG = "BETA_SCAN_ADMISSION_ENABLED";
export const COORDINATOR_TIMEOUT_MS = 8_000;

export const OUTCOME_CLAIMED = "claimed";
export const OUTCOME_REPLAYED = "replayed";
export const OUTCOME_BOUND = "bound";
export const OUTCOME_ALREADY_BOUND = "already_bound";
export const OUTCOME_RELEASED = "released";
export const OUTCOME_ALREADY_RELEASED = "already_released";

// Error codes the coordinator is allowed to hand back. Anything outside this
// set is collapsed to a generic code so an unexpected upstream body can never
// become a control-flow value in the Base44 function.
export const SAFE_COORDINATOR_ERRORS = new Set([
  "invalid_timestamp",
  "stale_request",
  "invalid_signature",
  "invalid_json",
  "invalid_payload",
  "request_too_large",
  "invalid_owner_user_id",
  "invalid_request_id",
  "invalid_request_fingerprint",
  "invalid_scan_id",
  "invalid_claim_token_format",
  "admission_busy",
  "request_conflict",
  "scan_identity_conflict",
  "barrier_generation_conflict",
  "invalid_claim_token",
  "claim_expired",
  "claim_not_found",
  "not_terminal_status",
  "scan_not_bound",
  "coordinator_unavailable",
  "scan_intake_paused",
]);

function readEnv(name) {
  const denoEnv = globalThis.Deno?.env;
  if (denoEnv && typeof denoEnv.get === "function") return String(denoEnv.get(name) ?? "");
  return String(globalThis.process?.env?.[name] ?? "");
}

/**
 * Fail closed. Admission is only active when the flag is exactly "true";
 * every other value, including "1", "TRUE" and unset, leaves it off.
 */
export function admissionEnabled(env = readEnv) {
  return env(ADMISSION_FLAG) === "true";
}

async function hmacBytes(secretBytes, payloadText) {
  const key = await crypto.subtle.importKey(
    "raw",
    secretBytes,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  return new Uint8Array(await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(payloadText),
  ));
}

/**
 * Two-step timestamped HMAC over the exact bytes that will be sent.
 *
 * The caller signs `payloadText` and then transmits that same string, so the
 * verifier never has to re-serialize a parsed body. That is what makes the
 * signature immune to key-ordering and number-formatting differences between
 * the JavaScript signer and the Python verifier.
 */
export async function admissionSignature(rootSecret, timestamp, payloadText) {
  const derivedKey = await hmacBytes(new TextEncoder().encode(rootSecret), ADMISSION_LABEL);
  const signature = await hmacBytes(derivedKey, `${timestamp}\n${payloadText}`);
  return Array.from(signature, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function canonicalize(value) {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value).sort().map((key) => [key, canonicalize(value[key])]),
    );
  }
  return value;
}

const CLAIM_EVIDENCE_KEYS = Object.freeze([
  "version",
  "owner_user_id",
  "request_id",
  "barrier_generation",
  "claim_sequence",
  "admission_mode",
  "acceptance_cohort_id",
  "acceptance_release_id",
  "acceptance_source_sha",
  "acceptance_expires_at",
]);

function exactClaimEvidenceShape(evidence) {
  if (!evidence || typeof evidence !== "object" || Array.isArray(evidence)) return false;
  const keys = Object.keys(evidence).sort();
  if (keys.length !== CLAIM_EVIDENCE_KEYS.length) return false;
  const expectedKeys = [...CLAIM_EVIDENCE_KEYS].sort();
  if (!keys.every((key, index) => key === expectedKeys[index])) return false;
  const barrier = Number(evidence.barrier_generation);
  const sequence = Number(evidence.claim_sequence);
  const expiresAt = evidence.acceptance_expires_at;
  const mode = String(evidence.admission_mode || "");
  return evidence.version === ADMISSION_CLAIM_EVIDENCE_VERSION
    && typeof evidence.owner_user_id === "string"
    && typeof evidence.request_id === "string"
    && Number.isInteger(barrier) && barrier >= 0
    && Number.isInteger(sequence) && sequence >= 0
    && ["open", "acceptance_only"].includes(mode)
    && typeof evidence.acceptance_cohort_id === "string"
    && typeof evidence.acceptance_release_id === "string"
    && typeof evidence.acceptance_source_sha === "string"
    && (expiresAt === null || (Number.isInteger(Number(expiresAt)) && Number(expiresAt) >= 0));
}

export async function admissionClaimEvidenceProof(evidence, rootSecret) {
  if (!exactClaimEvidenceShape(evidence) || !String(rootSecret || "")) return "";
  const canonical = JSON.stringify(canonicalize(evidence));
  const derivedKey = await hmacBytes(
    new TextEncoder().encode(String(rootSecret)),
    ADMISSION_CLAIM_EVIDENCE_LABEL,
  );
  const proof = await hmacBytes(derivedKey, canonical);
  return Array.from(proof, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function constantTimeHexEqual(left, right) {
  const a = String(left || "").toLowerCase();
  const b = String(right || "").toLowerCase();
  if (!/^[a-f0-9]{64}$/.test(a) || !/^[a-f0-9]{64}$/.test(b)) return false;
  let mismatch = 0;
  for (let index = 0; index < a.length; index += 1) {
    mismatch |= a.charCodeAt(index) ^ b.charCodeAt(index);
  }
  return mismatch === 0;
}

export async function verifyAdmissionClaimEvidence({ evidence, proof, signingKey } = {}) {
  if (!exactClaimEvidenceShape(evidence)) return false;
  try {
    const expected = await admissionClaimEvidenceProof(evidence, signingKey);
    return constantTimeHexEqual(proof, expected);
  } catch {
    return false;
  }
}

function normalizeError(value) {
  const code = String(value ?? "").trim();
  return SAFE_COORDINATOR_ERRORS.has(code) ? code : "coordinator_rejected";
}

async function callCoordinator(path, payload, { coordinatorUrl, signingKey, fetchImpl, timeoutMs = COORDINATOR_TIMEOUT_MS } = {}) {
  const baseUrl = String(coordinatorUrl ?? readEnv("SCAN_ADMISSION_COORDINATOR_URL")).replace(/\/+$/, "");
  const root = String(signingKey ?? readEnv("SCAN_EVIDENCE_SIGNING_KEY"));
  if (!baseUrl || !root) {
    return { ok: false, outcomeUnknown: false, failureCode: "admission_not_configured" };
  }

  const payloadText = JSON.stringify(payload);
  const timestamp = String(Math.trunc(Date.now() / 1000));

  let signature = "";
  try {
    signature = await admissionSignature(root, timestamp, payloadText);
  } catch {
    return { ok: false, outcomeUnknown: false, failureCode: "admission_sign_failed" };
  }

  const send = fetchImpl ?? globalThis.fetch;
  const controller = typeof AbortController === "function" ? new AbortController() : null;
  const timeout = Math.max(1, Number(timeoutMs) || COORDINATOR_TIMEOUT_MS);
  const timeoutHandle = controller ? setTimeout(() => controller.abort(), timeout) : null;
  let response;
  try {
    response = await send(`${baseUrl}${path}`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-fixlist-timestamp": timestamp,
        "x-fixlist-signature": signature,
      },
      body: payloadText,
      ...(controller ? { signal: controller.signal } : {}),
    });
  } catch {
    // The request may or may not have been applied. Callers must treat this as
    // unknown rather than retrying blind with different inputs.
    return { ok: false, outcomeUnknown: true, failureCode: "admission_unreachable" };
  } finally {
    if (timeoutHandle) clearTimeout(timeoutHandle);
  }

  let parsed = null;
  try {
    parsed = await response.json();
  } catch {
    parsed = null;
  }

  if (!response.ok) {
    return {
      ok: false,
      // A 5xx leaves the coordinator's state genuinely unknown; a 4xx is a
      // decision, and the decision is always "nothing was written".
      outcomeUnknown: response.status >= 500,
      failureCode: normalizeError(parsed?.error),
      retryAfterSeconds: Number(parsed?.retry_after_seconds) || 0,
      status: response.status,
    };
  }

  return { ok: true, outcomeUnknown: false, ...(parsed || {}) };
}

/**
 * Step 1 of admission. Wins, replays, or is told to wait. Creates nothing.
 */
export async function claimAdmission({ ownerUserId, requestId, requestFingerprint, ...options } = {}) {
  if (!admissionEnabled(options.env ?? readEnv)) {
    return { ok: false, outcomeUnknown: false, failureCode: "admission_disabled" };
  }
  return callCoordinator("/claim", {
    owner_user_id: String(ownerUserId ?? ""),
    request_id: String(requestId ?? ""),
    request_fingerprint: String(requestFingerprint ?? ""),
  }, options);
}

/**
 * Step 2. Binds the canonical server-created ScanRun id to the winning claim.
 * Requires the exact request id and claim token, so only the winner can bind.
 */
export async function bindAdmission({ ownerUserId, requestId, claimToken, scanId, barrierGeneration, ...options } = {}) {
  if (!admissionEnabled(options.env ?? readEnv)) {
    return { ok: false, outcomeUnknown: false, failureCode: "admission_disabled" };
  }
  return callCoordinator("/bind", {
    owner_user_id: String(ownerUserId ?? ""),
    request_id: String(requestId ?? ""),
    claim_token: String(claimToken ?? ""),
    scan_id: String(scanId ?? ""),
    barrier_generation: Number(barrierGeneration),
  }, options);
}

/**
 * Step 3. Frees admission once a scan is terminal.
 *
 * Called by the durable worker or the server watchdog -- never by a browser,
 * which is the entire point of moving terminal ownership off the client.
 */
export async function releaseAdmission({ ownerUserId, scanId, terminalStatus, ...options } = {}) {
  if (!admissionEnabled(options.env ?? readEnv)) {
    return { ok: false, outcomeUnknown: false, failureCode: "admission_disabled" };
  }
  return callCoordinator("/release", {
    owner_user_id: String(ownerUserId ?? ""),
    scan_id: String(scanId ?? ""),
    terminal_status: String(terminalStatus ?? ""),
  }, options);
}

export async function statusAdmission({ ownerUserId, ...options } = {}) {
  if (!admissionEnabled(options.env ?? readEnv)) {
    return { ok: false, outcomeUnknown: false, failureCode: "admission_disabled" };
  }
  return callCoordinator("/status", {
    owner_user_id: String(ownerUserId ?? ""),
  }, options);
}

export async function satisfyUnboundAdmission({ ownerUserId, requestId, barrierGeneration, ...options } = {}) {
  if (!admissionEnabled(options.env ?? readEnv)) {
    return { ok: false, outcomeUnknown: false, failureCode: "admission_disabled" };
  }
  return callCoordinator("/satisfy-unbound", {
    owner_user_id: String(ownerUserId ?? ""),
    request_id: String(requestId ?? ""),
    barrier_generation: Number(barrierGeneration),
  }, options);
}
