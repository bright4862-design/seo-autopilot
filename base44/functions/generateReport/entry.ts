import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

const GOOGLE_CLIENT_ID = Deno.env.get("GOOGLE_CLIENT_ID") || "";
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

    if (!GOOGLE_REDIRECT_URI) {
      return Response.json(
        {
          success: false,
          error: "GOOGLE_REDIRECT_URI is not configured in Base44 secrets.",
        },
        { status: 500 }
      );
    }

    const state = btoa(
      JSON.stringify({
        user_email: user.email || "",
        user_id: user.id || "",
        created_at: new Date().toISOString(),
        nonce: crypto.randomUUID(),
      })
    );

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