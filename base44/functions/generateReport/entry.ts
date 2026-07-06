import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

const GOOGLE_CLIENT_ID = Deno.env.get("GOOGLE_CLIENT_ID") || "";
const GOOGLE_CLIENT_SECRET = Deno.env.get("GOOGLE_CLIENT_SECRET") || "";
const GOOGLE_REDIRECT_URI = Deno.env.get("GOOGLE_REDIRECT_URI") || "";

const GSC_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly";

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();

    if (!user) {
      return Response.json(
        {
          success: false,
          error: "Unauthorized",
        },
        { status: 401 }
      );
    }

    if (!GOOGLE_CLIENT_ID) {
      return Response.json(
        {
          success: false,
          error: "GOOGLE_CLIENT_ID is not configured in Base44 secrets.",
        },
        { status: 500 }
      );
    }

    if (!GOOGLE_CLIENT_SECRET) {
      return Response.json(
        {
          success: false,
          error: "GOOGLE_CLIENT_SECRET is not configured in Base44 secrets.",
        },
        { status: 500 }
      );
    }

    if (!GOOGLE_REDIRECT_URI) {
      return Response.json(
        {
          success: false,
          error: "GOOGLE_REDIRECT_URI is not configured in Base44 secrets.",
        },
        { status: 500 }
      );
    }

    const state = await buildOAuthState(user);

    const authUrl = new URL("https://accounts.google.com/o/oauth2/v2/auth");

    authUrl.searchParams.set("client_id", GOOGLE_CLIENT_ID);
    authUrl.searchParams.set("redirect_uri", GOOGLE_REDIRECT_URI);
    authUrl.searchParams.set("response_type", "code");
    authUrl.searchParams.set("scope", GSC_SCOPE);
    authUrl.searchParams.set("access_type", "offline");
    authUrl.searchParams.set("prompt", "consent");
    authUrl.searchParams.set("include_granted_scopes", "true");
    authUrl.searchParams.set("state", state);

    return Response.json({
      success: true,
      auth_url: authUrl.toString(),
      oauth_state: state,
      redirect_uri: GOOGLE_REDIRECT_URI,
      scope: GSC_SCOPE,
    });
  } catch (error) {
    return Response.json(
      {
        success: false,
        error: error?.message || "googleSearchConsoleConnect failed",
      },
      { status: 500 }
    );
  }
});

async function buildOAuthState(user) {
  const payload = {
    user_email: user.email || "",
    user_id: user.id || "",
    created_at: new Date().toISOString(),
    nonce: crypto.randomUUID(),
  };

  const encodedPayload = base64UrlEncode(JSON.stringify(payload));
  const signature = await signStatePayload(encodedPayload);

  return `${encodedPayload}.${signature}`;
}

async function signStatePayload(encodedPayload) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(GOOGLE_CLIENT_SECRET),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );

  const signature = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(encodedPayload)
  );

  return base64UrlEncodeBytes(new Uint8Array(signature));
}

function base64UrlEncode(value) {
  return base64UrlEncodeBytes(new TextEncoder().encode(String(value || "")));
}

function base64UrlEncodeBytes(bytes) {
  let binary = "";

  for (const byte of bytes) binary += String.fromCharCode(byte);

  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}