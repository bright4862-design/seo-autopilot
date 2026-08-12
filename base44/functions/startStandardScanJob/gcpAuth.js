// Minimal Google service-account OAuth exchange for the Base44 dispatcher.
//
// The Cloud Tasks REST API requires an OAuth 2 access token. A service-account
// JWT assertion by itself is not used as the bearer token: it is signed with
// RS256, exchanged at Google's token endpoint, and the returned short-lived
// access_token is sent to Cloud Tasks.

const CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform";
const DEFAULT_TOKEN_URI = "https://oauth2.googleapis.com/token";
const JWT_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:jwt-bearer";

function bytesToBase64Url(bytes) {
  let binary = "";
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
  }
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function textToBase64Url(value) {
  return bytesToBase64Url(new TextEncoder().encode(value));
}

function decodeBase64Text(value) {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return new TextDecoder().decode(bytes);
}

export function parseServiceAccountKey(rawKey) {
  const source = String(rawKey || "").trim();
  if (!source) throw new Error("Missing service-account key.");

  let parsed;
  try {
    parsed = JSON.parse(source);
  } catch {
    parsed = JSON.parse(decodeBase64Text(source));
  }

  const clientEmail = String(parsed?.client_email || "").trim();
  const privateKey = String(parsed?.private_key || "").trim();
  const tokenUri = String(parsed?.token_uri || DEFAULT_TOKEN_URI).trim();
  if (!clientEmail || !privateKey || !tokenUri) throw new Error("Incomplete service-account key.");

  return {
    client_email: clientEmail,
    private_key: privateKey,
    token_uri: tokenUri,
  };
}

function pemToPkcs8(privateKeyPem) {
  const encoded = String(privateKeyPem || "")
    .replace(/-----BEGIN PRIVATE KEY-----/g, "")
    .replace(/-----END PRIVATE KEY-----/g, "")
    .replace(/\s+/g, "");
  if (!encoded) throw new Error("Invalid PKCS8 private key.");

  const binary = atob(encoded);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes.buffer;
}

export async function createServiceAccountJwt(rawKey, nowSeconds = Math.floor(Date.now() / 1000)) {
  const credentials = typeof rawKey === "string" ? parseServiceAccountKey(rawKey) : rawKey;
  const issuedAt = Math.floor(Number(nowSeconds));
  if (!Number.isFinite(issuedAt) || issuedAt <= 0) throw new Error("Invalid JWT issue time.");

  const header = textToBase64Url(JSON.stringify({ alg: "RS256", typ: "JWT" }));
  const claims = textToBase64Url(JSON.stringify({
    iss: credentials.client_email,
    scope: CLOUD_PLATFORM_SCOPE,
    aud: credentials.token_uri,
    iat: issuedAt,
    exp: issuedAt + 3600,
  }));
  const unsigned = `${header}.${claims}`;

  const key = await crypto.subtle.importKey(
    "pkcs8",
    pemToPkcs8(credentials.private_key),
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign(
    "RSASSA-PKCS1-v1_5",
    key,
    new TextEncoder().encode(unsigned),
  );

  return `${unsigned}.${bytesToBase64Url(new Uint8Array(signature))}`;
}

export async function createServiceAccountAccessToken(rawKey, options = {}) {
  let credentials;
  try {
    credentials = parseServiceAccountKey(rawKey);
  } catch {
    throw new Error("tasks_key_parse_failed");
  }

  let assertion;
  try {
    assertion = await createServiceAccountJwt(credentials, options.nowSeconds);
  } catch {
    throw new Error("tasks_jwt_sign_failed");
  }

  const fetchImpl = options.fetchImpl || fetch;
  let response;
  try {
    response = await fetchImpl(credentials.token_uri, {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ grant_type: JWT_GRANT_TYPE, assertion }).toString(),
    });
  } catch {
    throw new Error("tasks_token_endpoint_unreachable");
  }

  if (!response?.ok) throw new Error(`tasks_token_http_${Number(response?.status || 0)}`);
  const payload = await response.json().catch(() => null);
  const accessToken = String(payload?.access_token || "").trim();
  if (!accessToken) throw new Error("tasks_token_missing");
  return accessToken;
}
