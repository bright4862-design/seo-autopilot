const PROTOCOL = "fixlist_worker_runtime_v1";
const OUTER_FIELDS = ["runtime_request", "runtime_proof"];
const REQUEST_FIELDS = [
  "protocol", "function_name", "action", "nonce", "issued_at",
  "expected_build_id", "expected_runtime_activation_id", "payload",
];
const MAX_CLOCK_SKEW_SECONDS = 60;

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function exactFields(value, fields) {
  return isRecord(value) && Object.keys(value).length === fields.length
    && fields.every(field => Object.hasOwn(value, field));
}

function problem(status, code) {
  return Response.json({ success: false, error_code: code }, {
    status, headers: { "Cache-Control": "no-store" },
  });
}

export async function handleWorkerRuntime(body, identity, secret, { verify, sign }, invoke) {
  if (!exactFields(body, OUTER_FIELDS)) return problem(400, "worker_runtime_request_invalid");
  const request = body.runtime_request;
  if (!exactFields(request, REQUEST_FIELDS)
    || request.protocol !== PROTOCOL || request.function_name !== identity.function_name
    || !["identity", "invoke"].includes(request.action)
    || typeof request.nonce !== "string" || !/^[a-f0-9]{32}$/.test(request.nonce)
    || !Number.isSafeInteger(request.issued_at)
    || typeof request.expected_build_id !== "string" || !/^[a-f0-9]{64}$/.test(request.expected_build_id)
    || typeof request.expected_runtime_activation_id !== "string"
    || !/^[A-Za-z0-9._-]{1,120}$/.test(request.expected_runtime_activation_id)
    || (request.action === "identity" ? request.payload !== null : !isRecord(request.payload))) {
    return problem(400, "worker_runtime_request_invalid");
  }
  if (Math.abs(Math.floor(Date.now() / 1000) - request.issued_at) > MAX_CLOCK_SKEW_SECONDS) {
    return problem(409, "worker_runtime_request_stale");
  }
  if (!secret) return problem(503, "worker_runtime_not_configured");
  if (typeof body.runtime_proof !== "string" || !/^[a-f0-9]{64}$/.test(body.runtime_proof)
    || !await verify(request, secret, body.runtime_proof)) {
    return problem(403, "worker_runtime_proof_invalid");
  }

  const matches = request.expected_build_id === identity.build_id
    && request.expected_runtime_activation_id === identity.runtime_activation_id;
  const response = !matches ? problem(503, "worker_runtime_identity_mismatch")
    : request.action === "identity" ? Response.json({ success: true }) : await invoke(request.payload);
  const receipt = {
    protocol: PROTOCOL,
    function_name: identity.function_name,
    action: request.action,
    nonce: request.nonce,
    build_id: identity.build_id,
    runtime_activation_id: identity.runtime_activation_id,
    release_fingerprint: identity.release_fingerprint,
    http_status: response.status,
  };
  const proof = await sign(receipt, secret);
  const value = await response.json();
  const headers = new Headers(response.headers);
  headers.delete("Content-Length");
  headers.set("Cache-Control", "no-store");
  return Response.json({ ...value, _worker_runtime: { receipt, proof } }, {
    status: response.status, headers,
  });
}
