import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response(null, {
      status: 204,
      headers: CORS_HEADERS,
    });
  }

  const base44 = createClientFromRequest(req);
  const user = await base44.auth.me().catch(() => null);

  if (!user) {
    return jsonResponse(
      {
        success: false,
        error: "Unauthorized",
      },
      401
    );
  }

  return jsonResponse({
    success: false,
    disabled: true,
    message:
      "Google Search Console has been disabled. SEO Pilot now uses the website crawler, Screaming Frog Lite checks, and Gemini instead.",
  });
});

function jsonResponse(data: Record<string, unknown>, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      ...CORS_HEADERS,
      "Content-Type": "application/json; charset=utf-8",
    },
  });
}