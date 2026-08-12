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
  let source = String(rawKey || "").trim();
  if (!source) throw new Error("Missing service-account key.");

  // Be tolerant of the common ways secret UIs persist JSON: raw JSON, a JSON
  // string containing escaped JSON, KEY={...}, or base64-encoded JSON. Never
  // expose the value; just normalize it before extracting the three required
  // service-account fields.
  const assignmentPrefix = /^GCP_SERVICE_ACCOUNT_KEY\s*=\s*/;
  if (assignmentPrefix.test(source)) source = source.replace(assignmentPrefix, "").trim();

  const parseJsonLayers = (value) => {
    let current = value;
    for (let depth = 0; depth < 3; depth += 1) {
      if (current && typeof current === "object") return current;
      if (typeof current !== "string") break;
      current = JSON.parse(current.trim());
    }
    return current;
  };

  let parsed;
  try {
    parsed = parseJsonLayers(source);
  } catch {
    try {
      parsed = parseJsonLayers(decodeBase64Text(source));
    } catch {
      if (/\.json$/i.test(source) || source.startsWith("/") || source.startsWith("~")) {
        throw new Error("tasks_key_looks_like_path");
      }
      if (/-----BEGIN (?:RSA )?PRIVATE KEY-----/.test(source)) {
        throw new Error("tasks_key_private_key_only");
      }
      if (source.length < 200) {
        throw new Error("tasks_key_too_short");
      }
      throw new Error("tasks_key_unparseable");
    }
  }

  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("tasks_key_not_object");
  }

  const clientEmail = String(parsed?.client_email || "").trim();
  let privateKey = String(parsed?.private_key || "").trim();
  const tokenUri = String(parsed?.token_uri || DEFAULT_TOKEN_URI).trim();

  // Some secret editors preserve literal backslash-n sequences instead of
  // actual newlines. WebCrypto needs a valid PEM body, so normalize those.
  if (privateKey.includes("\\n") && !privateKey.includes("\n")) {
    privateKey = privateKey.replace(/\\n/g, "\n");
  }

  if (!clientEmail && !privateKey) throw new Error("tasks_key_fields_missing");
  if (!clientEmail) throw new Error("tasks_key_email_missing");
  if (!privateKey) throw new Error("tasks_key_private_key_missing");
  if (!tokenUri) throw new Error("tasks_key_token_uri_missing");

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
  } catch (error) {
    const safeCode = String(error?.message || "").trim();
    throw new Error(/^tasks_key_[a-z0-9_]+$/.test(safeCode) ? safeCode : "tasks_key_parse_failed");
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
