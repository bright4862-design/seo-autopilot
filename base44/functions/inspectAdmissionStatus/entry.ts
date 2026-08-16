const LABEL = "fixlist-admission-coordinator-v1";
async function hmacBytes(secretBytes: Uint8Array, payloadText: string) {
  const key = await crypto.subtle.importKey("raw", secretBytes, {name:"HMAC",hash:"SHA-256"}, false, ["sign"]);
  return new Uint8Array(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(payloadText)));
}
async function sig(root:string, ts:string, body:string) {
  const derived = await hmacBytes(new TextEncoder().encode(root), LABEL);
  const s = await hmacBytes(derived, `${ts}\n${body}`);
  return Array.from(s,b=>b.toString(16).padStart(2,"0")).join("");
}
Deno.serve(async (_req) => {
  const url=String(Deno.env.get("SCAN_ADMISSION_COORDINATOR_URL")||"").replace(/\/+$/,"");
  const root=String(Deno.env.get("SCAN_EVIDENCE_SIGNING_KEY")||"");
  if(!url||!root) return Response.json({ok:false,error:"config_missing"},{status:503});
  const payload=JSON.stringify({owner_user_id:"6a498da58ef5cec1f5cd4486"});
  const ts=String(Math.trunc(Date.now()/1000));
  const signature=await sig(root,ts,payload);
  const r=await fetch(`${url}/status`,{method:"POST",headers:{"content-type":"application/json","x-fixlist-timestamp":ts,"x-fixlist-signature":signature},body:payload});
  let parsed:any=null;try{parsed=await r.json()}catch{}
  return Response.json({ok:r.ok,http_status:r.status,admission:parsed?.admission||null,lease_active:parsed?.lease_active===true,error:String(parsed?.error||"")},{status:r.ok?200:503});
});
