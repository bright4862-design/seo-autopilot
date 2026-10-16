import { stableSerialize } from "./projection.js";

const REQUEST_LIMIT = 4_100_000;
const RESPONSE_LIMIT = 65_536;
const RESPONSE_SKEW_SECONDS = 300;
const COUNT_KEYS = ["fixed", "still_detected", "new_or_came_back", "came_back", "could_not_verify"];
const encoder = new TextEncoder();
const GATEWAY_SUPPORT_REFERENCES = new Set([
  "CMP-CONFIG", "CMP-TIMEOUT", "CMP-NETWORK", "CMP-GATEWAY-AUTH", "CMP-GATEWAY-ROUTE",
  "CMP-GATEWAY-LIMIT", "CMP-GATEWAY-BUSY", "CMP-GATEWAY-ERROR", "CMP-GATEWAY-INPUT", "CMP-GATEWAY-REDIRECT", "CMP-RESPONSE",
]);

// Diagnostics are fixed classifications, never exception text or customer data.
function networkErrorKind(error) {
  try {
    const code = typeof error?.cause?.code === "string" ? error.cause.code : error?.code;
    const codes = { ENOTFOUND: "dns", EAI_AGAIN: "dns", ECONNREFUSED: "connection_refused",
      ECONNRESET: "connection_reset", ENETUNREACH: "unreachable", EHOSTUNREACH: "unreachable",
      ETIMEDOUT: "network_timeout", CERT_HAS_EXPIRED: "tls", DEPTH_ZERO_SELF_SIGNED_CERT: "tls" };
    if (typeof code === "string" && Object.hasOwn(codes, code)) return codes[code];
    // Deno commonly supplies a TypeError with a message instead of a cause code.
    // Match bounded text locally; only the fixed category can leave this helper.
    const message = [error?.message, error?.cause?.message]
      .filter((value) => typeof value === "string").map((value) => value.slice(0, 4096)).join(" ");
    for (const [kind, pattern] of [
      ["dns", /\bdns\b|\bgetaddrinfo\b/i],
      ["tls", /\bcertificate\b|\btls\b|\bssl\b/i],
      ["connection_refused", /connection refused/i],
      ["connection_reset", /connection reset|connection closed|connection interrupted/i],
      ["unreachable", /network unreachable|host unreachable/i],
      ["permission", /permission denied|requires net access|notcapable/i],
      ["request_size", /(?:body|payload|request entity) too large/i],
      ["binding", /illegal invocation/i],
    ]) if (pattern.test(message)) return kind;
  } catch { /* Even an unusual thrown object must preserve the safe failure. */ }
  return "unknown";
}

function emitDiagnostic(callback, record) {
  try {
    if (typeof callback === "function") Promise.resolve(callback(record)).catch(() => {});
  } catch { /* Logging must not affect the optional comparison read. */ }
}

// Carry only a fixed support code across the optional-read boundary. Never keep
// the original exception, response body, URL or signed request on this error.
class ComparisonGatewayError extends Error {
  constructor(reference) {
    super("Scan comparison is unavailable.");
    this.name = "ComparisonGatewayError";
    this.support_reference = GATEWAY_SUPPORT_REFERENCES.has(reference) ? reference : "CMP-GATEWAY-ERROR";
  }
}

export function comparisonGatewaySupportReference(error) {
  return error instanceof ComparisonGatewayError && GATEWAY_SUPPORT_REFERENCES.has(error.support_reference)
    ? error.support_reference : "CMP-GATEWAY-ERROR";
}

function gatewayStatusReference(status) {
  if (status >= 300 && status < 400) return "CMP-GATEWAY-REDIRECT";
  if (status === 401 || status === 403) return "CMP-GATEWAY-AUTH";
  if (status === 404) return "CMP-GATEWAY-ROUTE";
  if (status === 413) return "CMP-GATEWAY-LIMIT";
  if (status === 422) return "CMP-GATEWAY-INPUT";
  if (status === 429) return "CMP-GATEWAY-BUSY";
  return "CMP-GATEWAY-ERROR";
}

function exactKeys(value, keys) {
  return value && typeof value === "object" && !Array.isArray(value)
    && Object.keys(value).length === keys.length
    && keys.every((key) => Object.hasOwn(value, key));
}

async function hmac(secretBytes, text) {
  const key = await crypto.subtle.importKey("raw", secretBytes, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return new Uint8Array(await crypto.subtle.sign("HMAC", key, encoder.encode(text)));
}

function hex(bytes) {
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function verifyResponseProof(payload, proof, rootSecret) {
  if (typeof proof !== "string" || !/^[a-f0-9]{64}$/.test(proof)) return false;
  const derived = await hmac(encoder.encode(rootSecret), "fixlist-scan-comparison-response-v1");
  const key = await crypto.subtle.importKey("raw", derived, { name: "HMAC", hash: "SHA-256" }, false, ["verify"]);
  return crypto.subtle.verify(
    "HMAC", key, Uint8Array.from(proof.match(/../g), (byte) => parseInt(byte, 16)), encoder.encode(stableSerialize(payload)),
  );
}

function safePresentation(value, currentScanId, previousScanId) {
  if (!exactKeys(value, [
    "version", "previous_scan_id", "current_scan_id", "headline", "score_line", "sample_line", "score_caution",
    "counts", "new_or_came_back_label", "new_or_came_back_is_verified_claim", "score_direction_claim_allowed",
    "overall_improvement_or_regression_claim",
  ]) || value.version !== "scan_comparison_presentation_v1"
      || value.current_scan_id !== currentScanId || value.previous_scan_id !== previousScanId
      || value.score_direction_claim_allowed !== false || value.new_or_came_back_is_verified_claim !== false
      || value.overall_improvement_or_regression_claim !== null
      || !exactKeys(value.counts, COUNT_KEYS)) throw new Error("comparison_presentation_invalid");
  for (const key of ["headline", "score_line", "sample_line", "score_caution", "new_or_came_back_label"]) {
    if (typeof value[key] !== "string" || !value[key].trim() || value[key].length > 1_000) {
      throw new Error("comparison_presentation_invalid");
    }
  }
  if (/\b(?:better|worse|improved|improvement|regressed|regression|declined|deteriorated|up by|down by)\b/i.test(value.score_line)) {
    throw new Error("comparison_presentation_invalid");
  }
  for (const key of COUNT_KEYS) {
    if (!Number.isSafeInteger(value.counts[key]) || value.counts[key] < 0 || value.counts[key] > 100) {
      throw new Error("comparison_presentation_invalid");
    }
  }
  if (value.counts.came_back > value.counts.new_or_came_back
      || value.counts.fixed + value.counts.still_detected + value.counts.came_back + value.counts.could_not_verify > 100) {
    throw new Error("comparison_presentation_invalid");
  }
  // Reconstruct the customer contract explicitly; never return the gateway
  // envelope, internal provenance, or an unchecked object from its response.
  return {
    version: value.version,
    previous_scan_id: previousScanId,
    current_scan_id: currentScanId,
    headline: value.headline,
    score_line: value.score_line,
    sample_line: value.sample_line,
    score_caution: value.score_caution,
    counts: Object.fromEntries(COUNT_KEYS.map((key) => [key, value.counts[key]])),
    new_or_came_back_label: "Unmatched or returned findings",
    new_or_came_back_is_verified_claim: false,
    score_direction_claim_allowed: false,
    overall_improvement_or_regression_claim: null,
  };
}

async function boundedJson(response) {
  const declaredLength = response.headers.get("content-length");
  if (declaredLength !== null && (!/^\d+$/.test(declaredLength) || Number(declaredLength) > RESPONSE_LIMIT)) {
    throw new Error("comparison_response_too_large");
  }
  if (!response.body) throw new Error("comparison_response_invalid");
  const reader = response.body.getReader();
  const chunks = [];
  let length = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > RESPONSE_LIMIT) throw new Error("comparison_response_too_large");
      chunks.push(value);
    }
  } catch (error) {
    await reader.cancel().catch(() => {});
    throw error;
  } finally {
    reader.releaseLock();
  }
  const bytes = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
}

/** Service-only transport. Inputs come exclusively from verified entity reads. */
export async function requestScanComparison({
  gatewayUrl, signingKey, pair, fetchImpl = fetch, now = Date.now, deadlineMs = 8_000, onDiagnostic,
}) {
  const startedAt = performance.now();
  let stage = "CMP-CONFIG";
  let requestBytes = 0;
  let httpStatus = null;
  let gatewayOriginFingerprint = null;
  let controller;
  let timer;
  try {
    if (typeof signingKey !== "string" || !signingKey) throw new ComparisonGatewayError("CMP-CONFIG");
    if (!exactKeys(pair, [
      "expected_owner_user_id", "expected_project_id", "expected_current_scan_id", "current_previous_scan_id",
      "previous_snapshot", "previous_proof", "current_snapshot", "current_proof",
    ])) throw new ComparisonGatewayError("CMP-GATEWAY-INPUT");
    const target = new URL(gatewayUrl);
    if (target.protocol !== "https:" || target.username || target.password || target.search || target.hash
        || !["", "/"].includes(target.pathname)) throw new ComparisonGatewayError("CMP-CONFIG");
    gatewayOriginFingerprint = hex(new Uint8Array(await crypto.subtle.digest("SHA-256", encoder.encode(target.origin)))).slice(0, 16);
    target.pathname = "/compare";
    const nonce = hex(crypto.getRandomValues(new Uint8Array(16)));
    const payload = { version: "scan_comparison_request_v1", nonce, ...pair };
    if (!exactKeys(payload, [
      "version", "nonce", "expected_owner_user_id", "expected_project_id", "expected_current_scan_id",
      "current_previous_scan_id", "previous_snapshot", "previous_proof", "current_snapshot", "current_proof",
    ])) throw new ComparisonGatewayError("CMP-GATEWAY-INPUT");
    stage = "CMP-GATEWAY-INPUT";
    const body = JSON.stringify(payload);
    requestBytes = encoder.encode(body).byteLength;
    if (requestBytes > REQUEST_LIMIT) throw new ComparisonGatewayError("CMP-GATEWAY-LIMIT");
    stage = "CMP-CONFIG";
    const timestamp = String(Math.floor(now() / 1_000));
    const derived = await hmac(encoder.encode(signingKey), "fixlist-scan-comparison-request-v1");
    const signature = hex(await hmac(derived, `${timestamp}\n${body}`));
    controller = new AbortController();
    timer = setTimeout(() => controller.abort(), deadlineMs);
    stage = "CMP-NETWORK";
    const response = await fetchImpl(target.href, {
      // Observe the redirect status but never forward signed evidence elsewhere.
      method: "POST", redirect: "manual", signal: controller.signal,
      headers: { "content-type": "application/json", "x-fixlist-timestamp": timestamp, "x-fixlist-signature": signature },
      body,
    });
    httpStatus = response.status;
    if (!response.ok) {
      // Do not read the body or Location. Cancellation must not delay failure.
      try { Promise.resolve(response.body?.cancel()).catch(() => {}); } catch { /* Best effort. */ }
      throw new ComparisonGatewayError(gatewayStatusReference(response.status));
    }
    stage = "CMP-RESPONSE";
    const envelope = await boundedJson(response);
    const result = envelope?.payload;
    if (!exactKeys(envelope, ["payload", "proof"])
        || !exactKeys(result, ["version", "nonce", "current_scan_id", "previous_scan_id", "presentation", "source_sha", "generated_at"])
        || result.version !== "scan_comparison_response_v1" || result.nonce !== nonce
        || result.current_scan_id !== pair.expected_current_scan_id || result.previous_scan_id !== pair.current_previous_scan_id
        || typeof result.source_sha !== "string" || !/^[a-f0-9]{40}$/.test(result.source_sha)
        || !Number.isSafeInteger(result.generated_at) || Math.abs(Math.floor(now() / 1_000) - result.generated_at) > RESPONSE_SKEW_SECONDS
        || !await verifyResponseProof(result, envelope.proof, signingKey)) throw new Error("comparison_response_invalid");
    return safePresentation(result.presentation, pair.expected_current_scan_id, pair.current_previous_scan_id);
  } catch (error) {
    let reference = stage;
    try { if (error instanceof ComparisonGatewayError) reference = comparisonGatewaySupportReference(error); } catch { /* Unknown throwable. */ }
    const localAborted = controller?.signal.aborted === true;
    if (localAborted) reference = "CMP-TIMEOUT";
    emitDiagnostic(onDiagnostic, {
      event: "scan_comparison_transport_failure_v1", reference, stage,
      request_bytes: requestBytes,
      elapsed_ms: Math.min(300_000, Math.max(0, Math.round(performance.now() - startedAt))),
      local_aborted: localAborted,
      http_status: Number.isInteger(httpStatus) && httpStatus >= 100 && httpStatus <= 599 ? httpStatus : null,
      gateway_origin_fingerprint: gatewayOriginFingerprint,
      network_error_kind: stage === "CMP-NETWORK" && httpStatus === null ? networkErrorKind(error) : "not_applicable",
    });
    throw new ComparisonGatewayError(reference);
  } finally {
    clearTimeout(timer);
  }
}
