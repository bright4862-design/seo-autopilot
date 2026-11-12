import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { summarizeStagedRuntime } from "../../base44/functions/fixlistStagedRuntimeControl/runtimeConfig.js";

const OWNER_ID = "6a498da58ef5cec1f5cd4486";
function state(env={},secret={}) {
  return summarizeStagedRuntime({
    readEnv: key => env[key],
    readSecret: key => secret[key],
    expectedOwnerId: OWNER_ID,
  });
}
const off = {SCAN_PIPELINE_MODE:"monolith",SCAN_STAGED_OWNER_IDS:""};
const on = {SCAN_PIPELINE_MODE:"staged",SCAN_STAGED_OWNER_IDS:OWNER_ID};
const gates = {BETA_SCAN_INTAKE_ENABLED:"false",BETA_SCAN_ADMISSION_ENABLED:"true"};

test("owner-only probe reports a closed monolith baseline with observed values",()=>{
  const result = state(off,{...off,...gates});
  assert.equal(result.config_converged,true);
  assert.equal(result.env_mode,"monolith");
  assert.equal(result.owner_match,false);
  assert.equal(result.intake_disabled_verified,true);
  assert.equal(result.admission_gate,"enabled");
  assert.equal(result.v9_runtime_attested,false);
});

test("explicit staged owner and closed customer intake are independent states",()=>{
  const result = state(on,{...on,...gates});
  assert.equal(result.config_converged,true);
  assert.equal(result.owner_match,true);
  assert.equal(result.cohort_count,1);
  assert.equal(result.staged_owner_enabled,true);
  assert.equal(result.intake_disabled_verified,true);
  assert.equal(result.new_owner_intake_disabled,true);
  const serialized=JSON.stringify(result);
  assert.equal(serialized.includes(OWNER_ID),false);
});

test("secret-only staged mode is not proof that V9 Deno env uses those values",()=>{
  const report=state({}, {...on,...gates});
  assert.equal(report.secret_mode,"staged");
  assert.equal(report.env_mode,"unavailable");
  assert.equal(report.config_converged,false);
  assert.equal(report.owner_match,false);
});
test("env-only staged mode is not a converged configuration",()=>{
  const report=state(on,gates);
  assert.equal(report.config_converged,false);
  assert.equal(report.owner_match,false);
});
test("cohort membership disagreement fails closed without printing either list",()=>{
  const report=state(on,{...on,SCAN_STAGED_OWNER_IDS:"other_owner",...gates});
  assert.equal(report.config_converged,false);
  assert.equal(report.owner_match,false);
  assert.equal(JSON.stringify(report).includes(OWNER_ID),false);
});
test("conflicting runtime modes fail closed",()=>{
  const report=state(on,{...off,...gates});
  assert.equal(report.config_converged,false);
  assert.equal(report.owner_match,false);
});
for(const owners of ["*",OWNER_ID+",*",OWNER_ID+","+OWNER_ID,"other_owner,"+OWNER_ID+",",...[
  "a", " ".repeat(4), ",".repeat(10), "u".repeat(65), "owner!wrong"
]]) {
  test("invalid or ambiguous cohort cannot grant access: "+JSON.stringify(owners),()=>{
    const settings={SCAN_PIPELINE_MODE:"staged",SCAN_STAGED_OWNER_IDS:owners};
    const result=state(settings,{...settings,...gates});
    assert.equal(result.owner_match,false);
    assert.equal(result.staged_owner_enabled,false);
  });
}
test("legacy owner alias does not silently create a staged cohort",()=>{
  const settings={...on,SCAN_PIPELINE_OWNER_IDS:OWNER_ID};
  const result=state(settings,{...on,...gates});
  assert.equal(result.config_converged,false);
  assert.equal(result.owner_match,false);
});
test("invalid mode and unknown intake are explicit unverified states",()=>{
  const report=state({...off,SCAN_PIPELINE_MODE:"hybrid"},{...off,BETA_SCAN_INTAKE_ENABLED:"enabled"});
  assert.equal(report.env_mode,"invalid");
  assert.equal(report.intake_gate,"invalid");
  assert.equal(report.intake_disabled_verified,false);
  assert.equal(report.config_converged,false);
});
test("missing intake does not claim disabled even with valid monolith config",()=>{
  const report=state(off,off);
  assert.equal(report.config_converged,true);
  assert.equal(report.intake_gate,"unavailable");
  assert.equal(report.intake_disabled_verified,false);
});
test("throwing or unavailable readers are not silently treated as disabled",()=>{
  const report=summarizeStagedRuntime({readEnv:()=>{throw Error("disabled");},readSecret:()=>{throw Error("staged");},expectedOwnerId:OWNER_ID});
  assert.equal(report.config_converged,false);
  assert.equal(report.intake_disabled_verified,false);
  assert.equal(report.owner_match,false);
  assert.doesNotMatch(JSON.stringify(report),/disabled\x22[,}].*intake_disabled_verified\x22:true/);
});
test("invalid requested owner is rejected before reading configuration",()=>{
  assert.throws(()=>summarizeStagedRuntime({readEnv:()=>"",readSecret:()=>"",expectedOwnerId:"*"}),/expected_owner_invalid/);
});
test("operator source is owner-authenticated, read-only, and emits no cohort secrets",()=>{
  const src=readFileSync("base44/functions/fixlistStagedRuntimeControl/entry.ts","utf8");
  assert.match(src,/createClientFromRequest\(req\)/);
  assert.match(src,/base44\.auth\.me\(\)/);
  assert.match(src,/user\?\.id !== OWNER_USER_ID/);
  assert.match(src,/user\?\.role/);
  assert.match(src,/input\.action !== "status"/);
  assert.doesNotMatch(src,/asServiceRole|\.update\(|\.create\(/);
});
test("operator shell only changes staged config and intake, never admission release or traffic",()=>{
  const src=readFileSync("scripts/operate-base44-staged-runtime.sh","utf8");
  assert.match(src,/fixlist_require_exact_main/);
  assert.match(src,/fixlist_require_base44_owner/);
  assert.match(src,/functions deploy fixlistStagedRuntimeControl/);
  assert.match(src,/SCAN_PIPELINE_MODE=monolith/);
  assert.match(src,/SCAN_STAGED_OWNER_IDS=/);
  assert.match(src,/BETA_SCAN_INTAKE_ENABLED=false/);
  assert.doesNotMatch(src,/secrets set[^\n]*BETA_SCAN_ADMISSION_ENABLED=/);
  for(const unsafe of ["gcloud run", "gcloud tasks", "update-traffic", "functions deploy startStandardScanJobV9",
                        "secrets set SCAN_EVIDENCE_SIGNING_KEY", "base44 deploy"]) {
    assert.equal(src.includes(unsafe),false);
  }
  const check=spawnSync("bash",["-n","scripts/operate-base44-staged-runtime.sh"],{encoding:"utf8"});
  assert.equal(check.status,0,check.stderr);
});
test("the operator function remains a self-contained single Base44 package",()=>{
  const config=JSON.parse(readFileSync("base44/functions/fixlistStagedRuntimeControl/function.jsonc","utf8"));
  assert.deepEqual(config,{name:"fixlistStagedRuntimeControl",entry:"entry.ts"});
});
