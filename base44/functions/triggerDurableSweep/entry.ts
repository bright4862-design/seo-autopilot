import { createClientFromRequest } from "npm:@base44/sdk@0.8.40";

const enc = new TextEncoder();
function canonicalize(value: any): any {
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (Array.isArray(value)) return value.map(canonicalize);
  if (value && typeof value === "object") {
    return Object.keys(value).sort().reduce((out: any, key) => {
      const item = value[key];
      if (!["undefined","function","symbol"].includes(typeof item)) out[key] = canonicalize(item);
      return out;
    }, {});
  }
  return null;
}
function stableSerialize(value: any) { return JSON.stringify(canonicalize(value)); }
async function sign(payload: any, secret: string) {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), {name:"HMAC",hash:"SHA-256"}, false, ["sign"]);
  const sig = new Uint8Array(await crypto.subtle.sign("HMAC", key, enc.encode(stableSerialize(payload))));
  return Array.from(sig, b => b.toString(16).padStart(2,"0")).join("");
}

Deno.serve(async (req) => {
  const secret = String(Deno.env.get("SCAN_EVIDENCE_SIGNING_KEY") || "");
  if (!secret) return Response.json({ok:false, stage:"config", error:"signing_key_missing"},{status:503});
  const signedDocument = {version:"durable_standard150_control_v1", action:"sweep"};
  const proof = await sign(signedDocument, secret);
  const body = JSON.stringify({...signedDocument, proof});
  const base44 = createClientFromRequest(req);
  let r: Response;
  try {
    r = await base44.functions.fetch("/durableScanWorkerControl", {
      method:"POST",
      headers:{"content-type":"application/json","X-FixList-Worker":"scan_job_worker_v1_cloud_tasks"},
      body,
    });
  } catch (e) {
    return Response.json({ok:false, stage:"invoke", error:String(e?.message||e)}, {status:503});
  }
  let parsed:any = null; try { parsed = await r.json(); } catch {}
  return Response.json({ok:r.ok,http_status:r.status,reconciliation:parsed?.reconciliation||parsed||null}, {status:r.ok?200:503});
});
