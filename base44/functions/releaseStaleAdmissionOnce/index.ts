import { createClientFromRequest } from "npm:@base44/sdk@0.8.40";
import { releaseAdmission } from "./admissionClient.js";

const ADMIN_ID = "6a498732ec779dfaaeab0e54";
const OWNER_ID = "6a498da58ef5cec1f5cd4486";
const SCAN_ID = "6a830cb7ee4ca623fca6267f";
const TERMINAL = new Set(["complete", "limited", "failed", "cancelled"]);

Deno.serve(async (req) => {
  if (req.method !== "POST") return Response.json({ success: false, error: "method_not_allowed" }, { status: 405 });
  const base44 = createClientFromRequest(req);
  const caller = await base44.auth.me().catch(() => null);
  if (String(caller?.id || "") !== ADMIN_ID) {
    return Response.json({ success: false, error: "unauthorized" }, { status: 403 });
  }
  const scan = await base44.asServiceRole.entities.ScanRun.get(SCAN_ID).catch(() => null);
  const status = String(scan?.status || "").trim().toLowerCase();
  if (!scan || String(scan?.id || "") !== SCAN_ID || String(scan?.owner_user_id || "") !== OWNER_ID) {
    return Response.json({ success: false, error: "scan_identity_mismatch" }, { status: 409 });
  }
  if (!TERMINAL.has(status) || !String(scan?.admission_access_id || "").trim()) {
    return Response.json({ success: false, error: "scan_not_releasable", status }, { status: 409 });
  }
  const result = await releaseAdmission({ ownerUserId: OWNER_ID, scanId: SCAN_ID, terminalStatus: status });
  if (!result?.ok || !["released", "already_released"].includes(String(result?.outcome || ""))) {
    return Response.json({ success: false, error: String(result?.failureCode || "release_failed"), outcome: String(result?.outcome || "") }, { status: 409 });
  }
  return Response.json({ success: true, scan_id: SCAN_ID, terminal_status: status, outcome: String(result.outcome) });
});
