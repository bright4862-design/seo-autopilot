import assert from "node:assert/strict";
import { generateKeyPairSync, verify, webcrypto } from "node:crypto";
import test from "node:test";

if (!globalThis.crypto) globalThis.crypto = webcrypto;

import {
  createServiceAccountAccessToken,
  createServiceAccountJwt,
  parseServiceAccountKey,
} from "../../base44/functions/startStandardScanJob/gcpAuth.js";

const pair = generateKeyPairSync("rsa", { modulusLength: 2048 });
const privateKey = pair.privateKey.export({ type: "pkcs8", format: "pem" });
const credentials = {
  client_email: "fixlist-tasks@example-project.iam.gserviceaccount.com",
  private_key: String(privateKey),
  token_uri: "https://oauth2.googleapis.com/token",
};

function decodeBase64Url(value) {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
  return Buffer.from(padded, "base64");
}

test("service-account configuration accepts JSON or base64-encoded JSON", () => {
  assert.deepEqual(parseServiceAccountKey(JSON.stringify(credentials)), credentials);
  const encoded = Buffer.from(JSON.stringify(credentials), "utf8").toString("base64");
  assert.deepEqual(parseServiceAccountKey(encoded), credentials);
});

test("the Google OAuth assertion is RS256-signed with bounded claims", async () => {
  const now = 1_786_030_000;
  const assertion = await createServiceAccountJwt(credentials, now);
  const [headerPart, claimsPart, signaturePart] = assertion.split(".");

  assert.deepEqual(JSON.parse(decodeBase64Url(headerPart).toString("utf8")), { alg: "RS256", typ: "JWT" });
  assert.deepEqual(JSON.parse(decodeBase64Url(claimsPart).toString("utf8")), {
    iss: credentials.client_email,
    scope: "https://www.googleapis.com/auth/cloud-platform",
    aud: credentials.token_uri,
    iat: now,
    exp: now + 3600,
  });

  assert.equal(
    verify(
      "RSA-SHA256",
      Buffer.from(`${headerPart}.${claimsPart}`, "utf8"),
      pair.publicKey,
      decodeBase64Url(signaturePart),
    ),
    true,
  );
});

test("the signed assertion is exchanged for a short-lived OAuth access token", async () => {
  let request = null;
  const token = await createServiceAccountAccessToken(JSON.stringify(credentials), {
    nowSeconds: 1_786_030_000,
    fetchImpl: async (url, init) => {
      request = { url, init };
      return new Response(JSON.stringify({ access_token: "short-lived-access-token", expires_in: 3600 }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    },
  });

  assert.equal(token, "short-lived-access-token");
  assert.equal(request.url, credentials.token_uri);
  assert.equal(request.init.method, "POST");
  assert.equal(request.init.headers["content-type"], "application/x-www-form-urlencoded");

  const form = new URLSearchParams(request.init.body);
  assert.equal(form.get("grant_type"), "urn:ietf:params:oauth:grant-type:jwt-bearer");
  assert.equal(form.get("assertion").split(".").length, 3);
});

test("invalid credentials and rejected token exchanges fail closed", async () => {
  assert.equal(await createServiceAccountAccessToken("not-json-or-base64"), "");
  assert.equal(
    await createServiceAccountAccessToken(JSON.stringify(credentials), {
      fetchImpl: async () => new Response("denied", { status: 401 }),
    }),
    "",
  );
});
