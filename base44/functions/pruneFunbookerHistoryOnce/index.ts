import { createClientFromRequest } from "npm:@base44/sdk@0.8.41";

const OWNER = "6a498da58ef5cec1f5cd4486";
const PROJECT = "6a734036abf07464364db281";
const KEEP = [
  "6a832302751d487721715938",
  "6a830cb7ee4ca623fca6267f",
  "6a83059e8751220e09584d80",
];
const TERMINAL = new Set(["complete", "limited", "failed", "cancelled"]);
const ACTIVE = new Set(["queued", "crawling", "reviewing"]);

Deno.serve(async (req) => {
  if (req.method !== "POST") return Response.json({success:false,error:"method_not_allowed"},{status:405});
  const b44 = createClientFromRequest(req);
  const e = b44.asServiceRole.entities;
  const rows = await e.ScanRun.filter({ project_id: PROJECT, owner_user_id: OWNER }, "-created_date", 100);
  const ordered = Array.isArray(rows) ? rows : [];
  const top = ordered.slice(0, 3).map((r:any) => String(r?.id || ""));
  if (JSON.stringify(top) !== JSON.stringify(KEEP)) {
    return Response.json({success:false,error:"top_three_changed",top},{status:409});
  }
  const active = ordered.filter((r:any) => ACTIVE.has(String(r?.status || "").toLowerCase())).map((r:any)=>r.id);
  if (active.length) return Response.json({success:false,error:"active_scan_present",active},{status:409});

  const deleted:string[] = [];
  const skipped:string[] = [];
  for (const run of ordered.slice(3)) {
    const scanId = String(run?.id || "");
    const status = String(run?.status || "").toLowerCase();
    if (!scanId || KEEP.includes(scanId) || !TERMINAL.has(status)) { if (scanId) skipped.push(scanId); continue; }
    if (String(run?.owner_user_id || "") !== OWNER || String(run?.project_id || "") !== PROJECT) {
      return Response.json({success:false,error:"identity_mismatch",scan_id:scanId},{status:409});
    }

    const lists = await e.FixList.filter({ scan_run_id: scanId }, "-created_date", 50).catch(()=>[]);
    for (const list of lists || []) {
      if (String(list?.owner_user_id || "") !== OWNER || String(list?.project_id || "") !== PROJECT) continue;
      const items = await e.FixItem.filter({ fix_list_id: String(list.id) }, "-created_date", 200).catch(()=>[]);
      for (const item of items || []) {
        if (String(item?.owner_user_id || "") === OWNER && String(item?.project_id || "") === PROJECT && String(item?.scan_run_id || "") === scanId && item?.id) {
          await e.FixItem.delete(item.id);
        }
      }
      if (list?.id) await e.FixList.delete(list.id);
    }
    const remaining = await e.FixItem.filter({ scan_run_id: scanId }, "-created_date", 200).catch(()=>[]);
    for (const item of remaining || []) {
      if (String(item?.owner_user_id || "") === OWNER && String(item?.project_id || "") === PROJECT && item?.id) await e.FixItem.delete(item.id);
    }
    await e.ScanRun.delete(scanId);
    deleted.push(scanId);
  }
  return Response.json({success:true,kept:KEEP,deleted_count:deleted.length,deleted,skipped});
});
