// Independent Extended 500 admission issuer candidate. NOT deployed or listed
// in the Standard 150 release manifest. No customer-tier flag can enable it
// unless the separately configured Base44 secret is exactly "true".
import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";
import { secrets } from "base44:runtime";
import { issueExtended500Admission } from "./handler.js";

function readPrivate(name: string): string {
  try { return String(secrets.get(name) || ""); }
  catch { return ""; }
}

export default async function (req: Request): Promise<Response> {
  if (req.method !== "POST") {
    return Response.json({ success: false, admitted: false, code: "method_not_allowed" }, { status: 405 });
  }
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me().catch(() => null);
    if (!user?.id || !user?.email) {
      return Response.json({ success: false, admitted: false, code: "unauthorized" }, { status: 401 });
    }
    const raw = await req.text();
    if (raw.length > 2048) {
      return Response.json({ success: false, admitted: false, code: "request_too_large" }, { status: 413 });
    }
    let body;
    try { body = JSON.parse(raw); }
    catch { return Response.json({ success: false, admitted: false, code: "invalid_json" }, { status: 400 }); }

    const outcome = await issueExtended500Admission({
      body,
      user,
      entities: base44.asServiceRole.entities,
      secret: readPrivate,
    });
    // Signed entitlement/grant, Access rows and coordinator credentials are
    // NEVER returned to browser. Only non-authoritative dispatch state.
    return Response.json(outcome.payload, { status: outcome.status });
  } catch {
    return Response.json({
      success: false, admitted: false, code: "extended500_issuer_unavailable",
    }, { status: 503 });
  }
}
