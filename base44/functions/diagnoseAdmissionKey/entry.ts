const LABEL = "fixlist-admission-coordinator-v1";
async function hmacBytes(secretBytes: Uint8Array, payloadText: string) {
  const key = await crypto.subtle.importKey("raw", secretBytes, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return new Uint8Array(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(payloadText)));
}
async function signature(root: string, ts: string, body: string) {
  const derived = await hmacBytes(new TextEncoder().encode(root), LABEL);
  const sig = await hmacBytes(derived, `${ts}\n${body}`);
  return Array.from(sig, (b) => b.toString(16).padStart(2,"0")).join("");
}
Deno.serve(async (_req) => {
  const url = String(Deno.env.get("SCAN_ADMISSION_COORDINATOR_URL") || "").replace(/\/+$/, "");
  const root = String(Deno.env.get("SCAN_EVIDENCE_SIGNING_KEY") || "");
  if (!url || !root) return Response.json({ok:false, stage:"config", has_url:!!url, has_key:!!root}, {status:503});
  const payload = JSON.stringify({owner_user_id:"diag-owner-123", request_id:"", request_fingerprint:"diag"});
  const ts = String(Math.trunc(Date.now()/1000));
  const sig = await signature(root, ts, payload);
  const r = await fetch(`${url}/claim`, {method:"POST", headers:{"content-type":"application/json","x-fixlist-timestamp":ts,"x-fixlist-signature":sig}, body:payload});
  let parsed:any = null; try { parsed = await r.json(); } catch {}
  return Response.json({ok:r.status===400 && parsed?.error==="invalid_request_id", http_status:r.status, coordinator_error:String(parsed?.error||"")});
});
