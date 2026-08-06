const CORS_HEADERS = Object.freeze({
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
});

export function corsHeaders() {
  return { ...CORS_HEADERS };
}

export function jsonResponse(payload, status = 200) {
  return Response.json(payload, { status, headers: corsHeaders() });
}
