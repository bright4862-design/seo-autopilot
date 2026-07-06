const GOOGLE_CLIENT_ID = Deno.env.get("GOOGLE_CLIENT_ID") || "";
const GOOGLE_CLIENT_SECRET = Deno.env.get("GOOGLE_CLIENT_SECRET") || "";
const GOOGLE_REDIRECT_URI = Deno.env.get("GOOGLE_REDIRECT_URI") || "";
const GOOGLE_OAUTH_FINAL_REDIRECT =
  Deno.env.get("GOOGLE_OAUTH_FINAL_REDIRECT") || "/reports?gsc=connected";
const GOOGLE_OAUTH_STATE_MAX_AGE_MS = 10 * 60 * 1000;

Deno.serve(async (req) => {
  try {
    const url = new URL(req.url);
    const code = url.searchParams.get("code") || "";
    const state = url.searchParams.get("state") || "";
    const error = url.searchParams.get("error") || "";

    if (error) {
      return htmlResponse(
        buildErrorHtml(`Google returned an OAuth error: ${escapeHtml(error)}`)
      );
    }

    if (!code) {
      return htmlResponse(buildErrorHtml("Missing Google OAuth code."));
    }

    if (!state) {
      return htmlResponse(buildErrorHtml("Missing Google OAuth state."));
    }

    if (!GOOGLE_CLIENT_ID || !GOOGLE_CLIENT_SECRET || !GOOGLE_REDIRECT_URI) {
      return htmlResponse(
        buildErrorHtml(
          "Google OAuth secrets are missing. Configure GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REDIRECT_URI."
        )
      );
    }

    const statePayload = await verifyOAuthState(state);
    const tokenResponse = await exchangeCodeForTokens(code);

    if (!tokenResponse.access_token) {
      return htmlResponse(
        buildErrorHtml("Google did not return an access token.")
      );
    }

    const sites = await listSearchConsoleSites(tokenResponse.access_token);

    const connection = {
      connected: true,
      provider: "google_search_console",
      access_token: tokenResponse.access_token,
      refresh_token: tokenResponse.refresh_token || "",
      token_type: tokenResponse.token_type || "Bearer",
      expires_in: tokenResponse.expires_in || 3600,
      expires_at:
        Date.now() + Number(tokenResponse.expires_in || 3600) * 1000,
      scope: tokenResponse.scope || "",
      sites,
      selected_site: sites?.[0]?.siteUrl || "",
      connected_at: new Date().toISOString(),
      state_user_id: statePayload.user_id || "",
    };

    return htmlResponse(buildSuccessHtml(connection, state));
  } catch (error) {
    return htmlResponse(
      buildErrorHtml(
        error?.message || "Google Search Console callback failed."
      )
    );
  }
});

async function verifyOAuthState(state: string) {
  const [encodedPayload, signature] = String(state || "").split(".");

  if (!encodedPayload || !signature) {
    throw new Error("Invalid Google OAuth state.");
  }

  const expectedSignature = await signStatePayload(encodedPayload);

  if (!timingSafeEqual(signature, expectedSignature)) {
    throw new Error("Invalid Google OAuth state signature.");
  }

  const payload = JSON.parse(base64UrlDecode(encodedPayload));
  const createdAt = Date.parse(payload.created_at || "");

  if (!createdAt || Date.now() - createdAt > GOOGLE_OAUTH_STATE_MAX_AGE_MS) {
    throw new Error("Google OAuth state expired. Please reconnect.");
  }

  if (!payload.nonce || !payload.user_id) {
    throw new Error("Invalid Google OAuth state payload.");
  }

  return payload;
}

async function signStatePayload(encodedPayload: string) {
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

function base64UrlEncodeBytes(bytes: Uint8Array) {
  let binary = "";

  for (const byte of bytes) binary += String.fromCharCode(byte);

  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function base64UrlDecode(value: string) {
  const base64 = String(value || "").replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, "=");

  return atob(padded);
}

function timingSafeEqual(a: string, b: string) {
  if (a.length !== b.length) return false;

  let diff = 0;

  for (let i = 0; i < a.length; i++) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }

  return diff === 0;
}

async function exchangeCodeForTokens(code: string) {
  const body = new URLSearchParams();

  body.set("client_id", GOOGLE_CLIENT_ID);
  body.set("client_secret", GOOGLE_CLIENT_SECRET);
  body.set("code", code);
  body.set("grant_type", "authorization_code");
  body.set("redirect_uri", GOOGLE_REDIRECT_URI);

  const response = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body,
  });

  const json = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      `Google token exchange failed with status ${response.status}: ${
        json.error_description || json.error || "Unknown error"
      }`
    );
  }

  return json;
}

async function listSearchConsoleSites(accessToken: string) {
  const response = await fetch("https://www.googleapis.com/webmasters/v3/sites", {
    method: "GET",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      Accept: "application/json",
    },
  });

  const json = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      `Could not list Search Console sites: ${
        json.error?.message || response.status
      }`
    );
  }

  return Array.isArray(json.siteEntry) ? json.siteEntry : [];
}

function buildSuccessHtml(connection: Record<string, unknown>, state: string) {
  const safeConnection = JSON.stringify(connection).replace(/</g, "\\u003c");
  const safeRedirect = JSON.stringify(GOOGLE_OAUTH_FINAL_REDIRECT);
  const safeState = JSON.stringify(state);

  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Google Search Console Connected</title>
  </head>
  <body style="font-family: system-ui, -apple-system, BlinkMacSystemFont, sans-serif; padding: 40px;">
    <h1>Google Search Console connected</h1>
    <p>You can close this page if you are not redirected automatically.</p>

    <script>
      try {
        const connection = ${safeConnection};
        const returnedState = ${safeState};
        const expectedState = window.localStorage.getItem("seo_autopilot:gsc_oauth_state") || "";

        if (!expectedState || expectedState !== returnedState) {
          throw new Error("Google OAuth state did not match this browser session.");
        }

        window.localStorage.removeItem("seo_autopilot:gsc_oauth_state");
        window.localStorage.setItem("seo_autopilot:gsc_connection", JSON.stringify(connection));
        window.location.href = ${safeRedirect};
      } catch (error) {
        document.body.innerHTML = "<h1>Connection save failed</h1><p>" + String(error.message || error) + "</p>";
      }
    </script>
  </body>
</html>`;
}

function buildErrorHtml(message: string) {
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Google Search Console Error</title>
  </head>
  <body style="font-family: system-ui, -apple-system, BlinkMacSystemFont, sans-serif; padding: 40px;">
    <h1>Google Search Console connection failed</h1>
    <p>${escapeHtml(message)}</p>
    <p><a href="/reports">Go back to SEO Connections</a></p>
  </body>
</html>`;
}

function htmlResponse(html: string) {
  return new Response(html, {
    status: 200,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
    },
  });
}

function escapeHtml(value: string) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}