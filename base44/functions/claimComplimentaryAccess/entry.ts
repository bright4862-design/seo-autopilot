import { createClientFromRequest } from "npm:@base44/sdk@0.8.40";

const APP_ID = "6a498732ec779dfaaeab0e53";
const PLAN_ID = "standard150_lifetime";

function normalizeEmail(value) {
  return String(value || "").trim().toLowerCase();
}

function uniqueRecords(records) {
  return Array.from(new Map((records || []).filter(Boolean).map((record) => [String(record.id || ""), record])).values())
    .filter((record) => String(record.id || ""));
}

function isEligibleManualGrant(access, email) {
  return Boolean(
    access
    && normalizeEmail(access.user_email) === email
    && access.access_status === "active"
    && access.has_full_access === true
    && access.plan_id === PLAN_ID
    && access.app_id === APP_ID
    && access.grant_source === "manual_grant"
    && Number.isFinite(Date.parse(String(access.granted_at || "")))
  );
}

function publicAccess(access) {
  return {
    id: String(access?.id || ""),
    user_email: normalizeEmail(access?.user_email),
    owner_user_id: String(access?.owner_user_id || ""),
    access_status: String(access?.access_status || ""),
    plan_id: String(access?.plan_id || ""),
    grant_source: String(access?.grant_source || ""),
    app_id: String(access?.app_id || ""),
    has_full_access: access?.has_full_access === true,
    granted_at: String(access?.granted_at || ""),
  };
}

export default async function (req) {
  if (req.method !== "POST") {
    return Response.json({ success: false, code: "method_not_allowed" }, { status: 405 });
  }

  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me().catch(() => null);
    const userId = String(user?.id || "").trim();
    const email = normalizeEmail(user?.email);
    if (!userId || !email) {
      return Response.json({ success: false, code: "unauthorized" }, { status: 401 });
    }

    let rows = uniqueRecords(await base44.asServiceRole.entities.Access.filter({ user_email: email }));
    if (rows.length === 0) {
      return Response.json({ success: false, code: "complimentary_access_not_found" }, { status: 404 });
    }
    if (rows.length > 1) {
      return Response.json({ success: false, code: "access_conflict" }, { status: 409 });
    }

    let access = rows[0];
    if (!isEligibleManualGrant(access, email)) {
      return Response.json({ success: false, code: "complimentary_access_not_found" }, { status: 404 });
    }

    const currentOwner = String(access.owner_user_id || "").trim();
    if (currentOwner && currentOwner !== userId) {
      return Response.json({ success: false, code: "access_conflict" }, { status: 409 });
    }
    if (currentOwner === userId) {
      return Response.json({ success: true, claimed: false, access: publicAccess(access) });
    }

    await base44.asServiceRole.entities.Access.update(access.id, { owner_user_id: userId });
    rows = uniqueRecords(await base44.asServiceRole.entities.Access.filter({ user_email: email }));
    if (rows.length !== 1 || String(rows[0]?.id || "") !== String(access.id || "")) {
      return Response.json({ success: false, code: "access_conflict" }, { status: 409 });
    }
    access = rows[0];
    if (!isEligibleManualGrant(access, email) || String(access.owner_user_id || "").trim() !== userId) {
      return Response.json({ success: false, code: "access_conflict" }, { status: 409 });
    }

    return Response.json({ success: true, claimed: true, access: publicAccess(access) });
  } catch (error) {
    console.error("claimComplimentaryAccess failed", {
      name: String(error?.name || "claim_error").slice(0, 80),
      code: String(error?.code || "claim_failed").slice(0, 80),
    });
    return Response.json({ success: false, code: "claim_failed" }, { status: 500 });
  }
}
