const GOOGLE_CLIENT_ID = Deno.env.get("GOOGLE_CLIENT_ID") || "";
const GOOGLE_CLIENT_SECRET = Deno.env.get("GOOGLE_CLIENT_SECRET") || "";
const GOOGLE_REDIRECT_URI = Deno.env.get("GOOGLE_REDIRECT_URI") || "";
const GOOGLE_OAUTH_FINAL_REDIRECT =
  Deno.env.get("GOOGLE_OAUTH_FINAL_REDIRECT") || "/reports?gsc=connected";

Deno.serve(async (req) => {
  try {
    const url = new URL(req.url);
    const code = url.searchParams.get("code") || "";
    const error = url.searchParams.get("error") || "";

    if (error) {
      return htmlResponse(
        buildErrorHtml(`Google returned an OAuth error: ${escapeHtml(error)}`)
      );
    }

    if (!code) {
      return htmlResponse(buildErrorHtml("Missing Google OAuth code."));
    }

    if (!GOOGLE_CLIENT_ID || !GOOGLE_CLIENT_SECRET || !GOOGLE_REDIRECT_URI) {
      return htmlResponse(
        buildErrorHtml(
          "Google OAuth secrets are missing. Configure GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REDIRECT_URI."
        )
      );
    }

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
    };

    return htmlResponse(buildSuccessHtml(connection));
  } catch (error) {
    return htmlResponse(
      buildErrorHtml(
        error?.message || "Google Search Console callback failed."
      )
    );
  }
});

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

function buildSuccessHtml(connection: Record<string, unknown>) {
  const safeConnection = JSON.stringify(connection).replace(/</g, "\\u003c");
  const safeRedirect = JSON.stringify(GOOGLE_OAUTH_FINAL_REDIRECT);

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
        window.localStorage.setItem("seo_autopilot:gsc_connection", JSON.stringify(connection));
        window.location.href = ${safeRedirect};
      } catch (error) {
        document.body.innerHTML = "<h1>Connection saved failed</h1><p>" + String(error.message || error) + "</p>";
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