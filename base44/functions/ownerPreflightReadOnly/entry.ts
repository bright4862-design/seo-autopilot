import { createClientFromRequest } from "npm:@base44/sdk@0.8.40";

const OWNER_ID = "6a498da58ef5cec1f5cd4486";
const OWNER_EMAIL = "bright4862@gmail.com";
const APP_ID = "6a498732ec779dfaaeab0e53";
const PLAN_ID = "standard150_lifetime";
const FUNBOOKER_PROJECT_ID = "6a734036abf07464364db281";

function normDomain(v:string){try{return new URL(v).hostname.toLowerCase().replace(/^www\./,'')}catch{return ''}}
Deno.serve(async (req) => {
  const b44 = createClientFromRequest(req);
  const e = b44.asServiceRole.entities;
  const user = await e.User.get(OWNER_ID).catch(()=>null);
  const project = await e.BusinessProject.get(FUNBOOKER_PROJECT_ID).catch(()=>null);
  const accessRows = await e.Access.filter({owner_user_id:OWNER_ID}, "-created_date", 20).catch(()=>[]);
  const allowed = Array.from(new Set(String(Deno.env.get("BETA_COHORT_ALLOWED_USER_IDS")||"").split(/[\s,]+/).map(v=>v.trim()).filter(Boolean)));
  const row = Array.isArray(accessRows) && accessRows.length===1 ? accessRows[0] : null;
  const grantedAt = Date.parse(String(row?.granted_at||''));
  const entitlement = !!(
    row &&
    String(user?.email||'').trim().toLowerCase()===OWNER_EMAIL &&
    String(row?.user_email||'').trim().toLowerCase()===OWNER_EMAIL &&
    String(row?.owner_user_id||'')===OWNER_ID &&
    row?.has_full_access===true &&
    row?.access_status==='active' &&
    row?.plan_id===PLAN_ID &&
    row?.app_id===APP_ID &&
    row?.grant_source==='owner_test' &&
    Number.isFinite(grantedAt)
  );
  const queue=String(Deno.env.get("SCAN_TASKS_QUEUE_PATH")||'');
  const drain=String(Deno.env.get("SCAN_DRAIN_QUEUE_PATH")||'');
  const worker=String(Deno.env.get("SCAN_WORKER_URL")||'');
  const invoker=String(Deno.env.get("TASKS_INVOKER_SERVICE_ACCOUNT")||'');
  const gateway=String(Deno.env.get("SCAN_DISPATCH_GATEWAY_URL")||'');
  const coord=String(Deno.env.get("SCAN_ADMISSION_COORDINATOR_URL")||'');
  const signing=String(Deno.env.get("SCAN_EVIDENCE_SIGNING_KEY")||'');
  return Response.json({
    ok:true,
    owner:{exists:!!user,id_match:String(user?.id||'')===OWNER_ID,email_match:String(user?.email||'').toLowerCase()===OWNER_EMAIL},
    cohort:{enabled:String(Deno.env.get("BETA_SCAN_ADMISSION_ENABLED")||'').trim().toLowerCase()==='true',allowed_count:allowed.length,owner_allowed:allowed.includes(OWNER_ID),valid_count:allowed.length>=1&&allowed.length<=25},
    project:{exists:!!project,owner_match:String(project?.owner_user_id||'')===OWNER_ID,domain:normDomain(String(project?.website_url||'')),funbooker_domain_match:normDomain(String(project?.website_url||''))==='funbooker.com'},
    entitlement:{row_count:Array.isArray(accessRows)?accessRows.length:0,passes:entitlement,grant_source:String(row?.grant_source||''),status:String(row?.access_status||'')},
    runtime:{queue_present:!!queue,drain_present:!!drain,queues_distinct:!!queue&&!!drain&&queue!==drain,worker_scan_job:/\/scan-job$/.test(worker),invoker_present:!!invoker,gateway_present:!!gateway,coordinator_present:!!coord,signing_key_present:!!signing}
  });
});
