// Isolated owner-only readback. Does not modify admission, secrets or scans.
import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";
import { secrets } from "base44:runtime";
import { summarizeStagedRuntime } from "./runtimeConfig.js";

const OWNER_USER_ID = "6a498da58ef5cec1f5cd4486";
const OWNER_EMAIL = "bright4862@gmail.com";
const OPERATOR_BUILD_ID = "fixlist-staged-runtime-control-v1";

function response(body: Record<string, unknown>, status = 200): Response {
  return Response.json(body, { status, headers: { "Cache-Control": "no-store" } });
}

export default async function (req: Request): Promise<Response> {
  if (req.method !== "POST") return response({ success: false, error_code: "method_not_allowed" }, 405);
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me().catch(() => null);
    if (user?.id !== OWNER_USER_ID || String(user?.email || "").trim().toLowerCase() !== OWNER_EMAIL
        || String(user?.role || "").trim().toLowerCase() !== "admin") {
      return response({ success: false, error_code: "owner_only" }, 403);
    }
    const body = await req.json().catch(() => null);
    const input = body?.data && typeof body.data === "object" ? body.data : body;
    if (!input || input.action !== "status" || Object.keys(input).some(key => key !== "action")) {
      return response({ success: false, error_code: "invalid_action" }, 400);
    }
    const state = summarizeStagedRuntime({
      readEnv: name => Deno.env.get(name),
      readSecret: name => secrets.get(name),
      expectedOwnerId: OWNER_USER_ID,
    });
    return response({ success: true, operator_build_id: OPERATOR_BUILD_ID, ...state });
  } catch {
    return response({ success: false, error_code: "runtime_unavailable" }, 503);
  }
}
