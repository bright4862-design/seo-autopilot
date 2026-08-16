import { createServiceAccountAccessToken } from "../startStandardScanJob/gcpAuth.js";

function b64(s: string) {
  return btoa(unescape(encodeURIComponent(s)));
}

Deno.serve(async (_req) => {
  const rawKey = String(Deno.env.get("GCP_SERVICE_ACCOUNT_KEY") || "");
  const queuePath = String(Deno.env.get("SCAN_TASKS_QUEUE_PATH") || "").trim();
  const invoker = String(Deno.env.get("TASKS_INVOKER_SERVICE_ACCOUNT") || "").trim();
  const workerUrl = String(Deno.env.get("SCAN_WORKER_URL") || "").trim();
  if (!rawKey || !queuePath || !invoker || !workerUrl) {
    return Response.json({ok:false, stage:"config", has_key:!!rawKey, has_queue:!!queuePath, has_invoker:!!invoker, has_worker:!!workerUrl}, {status:503});
  }
  const origin = new URL(workerUrl).origin;
  const reconcileUrl = `${origin}/scan-reconcile`;
  let token = "";
  try { token = await createServiceAccountAccessToken(rawKey); }
  catch (e) { return Response.json({ok:false, stage:"oauth", error:String(e?.message||e)}, {status:503}); }
  const task = {
    httpRequest: {
      httpMethod: "POST",
      url: reconcileUrl,
      headers: {"Content-Type":"application/json"},
      body: b64("{}"),
      oidcToken: {serviceAccountEmail: invoker, audience: origin},
    },
  };
  const r = await fetch(`https://cloudtasks.googleapis.com/v2/${queuePath}/tasks`, {
    method:"POST",
    headers:{authorization:`Bearer ${token}`,"content-type":"application/json"},
    body:JSON.stringify({task}),
  });
  const parsed = await r.json().catch(()=>null);
  return Response.json({ok:r.ok,http_status:r.status, task_name:r.ok?String(parsed?.name||""):"", error:r.ok?"":String(parsed?.error?.status||parsed?.error?.message||"cloud_tasks_rejected")}, {status:r.ok?200:503});
});
