import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {webcrypto} from "node:crypto";
import test from "node:test";
import {resolveServerScanContract, trustedScanContract, validateScanResultCap, progressFields} from "../../base44/functions/startStandardScanJobV9/scanLimits.js";
import {topFixIds} from "../../base44/functions/getCustomerScanResultV9/firstFixes.js";
import {buildAuthoritySnapshot, buildPersistedAuthoritySnapshot} from "../../base44/functions/persistDurableScanAuthorityV9/authoritySnapshot.js";
import {buildAuthoritySnapshot as oldSnapshot} from "../../base44/functions/persistDurableScanAuthorityV8/authoritySnapshot.js";
import {authorityRowsFromSnapshot} from "../../base44/functions/persistDurableScanAuthorityV9/authorityRows.js";
import {authoritySnapshotFromRows, createAuthoritySeal, verifyAuthoritySeal, buildCustomerProjection} from "../../base44/functions/getCustomerScanResultV9/projection.js";
import {sanitizeComparisonEvidence, MISSING_H1_COMPARISON_EVIDENCE_VERSION, MISSING_H1_RULE, MISSING_H1_RULE_DEFINITION_VERSION, MISSING_H1_COMPARISON_PROFILE_VERSION} from "../../base44/functions/getCustomerScanResultV9/comparisonEvidence.js";
import {PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION} from "../../base44/functions/getCustomerScanResultV9/evidenceUrlIdentity.js";
import {ensureWorkspaceCleanup, workspaceCleanupTask} from "../../base44/functions/deleteCustomerScanDataV9/workspaceCleanup.js";
const geo = JSON.parse(readFileSync("tests/fixtures/geo/runtime.json", "utf8"));
const standard = {scan_mode:"standard_150", page_cap:150, pipeline_mode:"monolith"};
const large = {scan_mode:"standard_500", page_cap:500, pipeline_mode:"staged"};
const active = {has_full_access:true, access_status:"active", page_cap:500};
const env = name => ({SCAN_PIPELINE_MODE:"staged", SCAN_STAGED_OWNER_IDS:"owner, second"}[name] || "");

test("server grant and staged cohort jointly determine page cap, irrespective of request preference", () => {
  assert.deepEqual(resolveServerScanContract({access:active, ownerUserId:"owner",env}),large);
  assert.deepEqual(resolveServerScanContract({access:active, ownerUserId:"unlisted",env}),standard);
  assert.deepEqual(resolveServerScanContract({access:active, ownerUserId:"owner"}),standard);
  assert.equal(resolveServerScanContract({access:{...active,has_full_access:false},ownerUserId:"owner",env}).page_cap,150);
  assert.equal(resolveServerScanContract({access:active,ownerUserId:"owner",env,request:{page_cap:5_000}}).page_cap,500);
  assert.throws(() => trustedScanContract({...large,pipeline_mode:"monolith"}));
  assert.throws(() => trustedScanContract({...standard,page_cap:500}));
});

test("authorized page cap bounds actual result and review evidence, while legacy records retain 150", () => {
  assert.deepEqual(validateScanResultCap(large,{pages_crawled:500,scan_mode:"standard_500",page_cap:500},{geo_readiness:{sample_pages:500}}),large);
  for(const value of [-1,501,1.5,"500"]) assert.throws(() => validateScanResultCap(large,{pages_crawled:value}));
  assert.throws(() => validateScanResultCap(standard,{pages_crawled:151}));
  assert.throws(() => validateScanResultCap({}, {pages_crawled:151}));
  assert.throws(() => validateScanResultCap(large,{pages_crawled:500,scan_mode:"standard_150"}));
  assert.throws(() => validateScanResultCap(standard,{pages_crawled:150},{comparison_evidence:{observation_count:500}}));
});

test("batch progress is bounded, monotonic and heartbeat-bearing", () => {
  const result=progressFields({...large,pages_crawled:100,pages_planned:500},{pages_crawled:50,pages_planned:400});
  assert.equal(progressFields(large,{pages_crawled:407,pages_planned:500,batch_committed:10}).last_committed_batch,10);
  assert.equal(result.pages_crawled,100); assert.equal(result.pages_planned,500); assert.ok(Number.isFinite(Date.parse(result.worker_heartbeat_at)));
  for(const progress of [{pages_crawled:501,pages_planned:500},{pages_crawled:30,pages_planned:20},{pages_crawled:-1,pages_planned:500},{pages_crawled:50,pages_planned:NaN}]) assert.throws(() => progressFields(large,progress));
});

function snapshotArgs(contract={}) {return {scan:{...geo.scan,...contract,website_url:"https://example.com/",pages_found:500,pages_crawled:contract.page_cap || 150}, review:{geo_readiness:geo.assessed,health_score:93,recommendations:[]},identity:{scan_id:"scan_123",project_id:"project_123",normalized_domain:"example.com"},userId:"owner_123",now:"2026-11-11T12:00:00.000Z"};}
test("V9 cap refactor preserves historical 150 snapshot bytes and seals new cap through persistence",async() => {
  assert.deepEqual(buildAuthoritySnapshot(snapshotArgs()),oldSnapshot(snapshotArgs()));
  const snapshot=buildAuthoritySnapshot(snapshotArgs(large));
  const persisted=authorityRowsFromSnapshot(snapshot,{fixListId:"list_123",ownerUserId:"owner_123"});
  const rows={run:{...persisted.scanRun,id:"scan_123",project_id:"project_123"},fixList:{...persisted.fixList,id:"list_123"},fixItems:persisted.fixItems,userId:"owner_123"};
  assert.equal(snapshot.scan.page_cap,500);
  assert.deepEqual(buildPersistedAuthoritySnapshot(rows),snapshot);
  assert.deepEqual(authoritySnapshotFromRows(rows),snapshot);
  const proof=await createAuthoritySeal(snapshot,"test-key",webcrypto);
  assert.equal(await verifyAuthoritySeal(authoritySnapshotFromRows(rows),"test-key",proof,webcrypto),true);
  const projection=buildCustomerProjection({...rows,fullAccess:true,authorityVerified:true});
  assert.equal(projection.run.page_cap,500); assert.deepEqual(projection.top_fix_ids,[]);
  const tampered=structuredClone(rows);Object.assign(tampered.run,standard);
  assert.equal(await verifyAuthoritySeal(authoritySnapshotFromRows(tampered),"test-key",proof,webcrypto),false);
});

test("V9 comparison supports the complete 500-page observation population", () => {
  const observations=Array.from({length:500},(_,i)=>({page_url:`https://example.com/page-${i}`,status_code:200,content_type:"text/html",page_evidence_class:"usable_html",indexable:true,robots:"",h1_count:1,evaluated:true,applicable:true,finding_present:false}));
  const evidence={version:MISSING_H1_COMPARISON_EVIDENCE_VERSION,rule:MISSING_H1_RULE,rule_definition_version:MISSING_H1_RULE_DEFINITION_VERSION,comparison_profile_version:MISSING_H1_COMPARISON_PROFILE_VERSION,evidence_url_identity_version:PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION,observation_count:500,evaluated_page_count:500,finding_present_count:0,finding_absent_count:500,observations};
  assert.equal(sanitizeComparisonEvidence(evidence,{scanOrigin:"https://example.com",identityVersion:PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION}).observations.length,500);
  assert.throws(() => sanitizeComparisonEvidence({...evidence,observations:[...observations,observations[0]]},{scanOrigin:"https://example.com",identityVersion:PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION}));
});

test("first fixes vary root cause and template while guaranteeing an available owner action", () => {
  const fixes=[{fix_id:"a",canonical_action_rank:1,root_cause_id:"meta",page_template_family:"product"},{fix_id:"b",canonical_action_rank:2,root_cause_id:"meta",page_template_family:"blog"},{fix_id:"c",canonical_action_rank:3,root_cause_id:"h1",page_template_family:"blog"},{fix_id:"d",canonical_action_rank:4,root_cause_id:"link",page_template_family:"home"},{fix_id:"e",canonical_action_rank:5,root_cause_id:"social",page_template_family:"about",who_can_do_this:"you"}];
  assert.deepEqual(topFixIds(fixes),["a","c","e"]);
  assert.deepEqual(topFixIds(fixes),topFixIds(fixes));
});

const run={id:"scan_123",attempt_count:2,request_id:"request_123",project_id:"project_123",owner_user_id:"owner_123",website_url:"https://example.com/",pipeline_mode:"staged"};
const cleanupEnv=name=>({SCAN_DRAIN_QUEUE_PATH:"projects/example-project/locations/europe-west1/queues/stages",SCAN_WORKER_URL:"https://worker.example/scan-job",TASKS_INVOKER_SERVICE_ACCOUNT:"invoker@example.iam.gserviceaccount.com",GCP_SERVICE_ACCOUNT_KEY:"local-test-only"}[name] || "");
test("workspace deletion is queued with pinned target/OIDC and cannot claim completion before worker acknowledgment",async()=> {
  const body=workspaceCleanupTask({run,queuePath:cleanupEnv("SCAN_DRAIN_QUEUE_PATH"),workerUrl:cleanupEnv("SCAN_WORKER_URL"),invokerServiceAccount:cleanupEnv("TASKS_INVOKER_SERVICE_ACCOUNT")});
  assert.equal(body.task.httpRequest.url,"https://worker.example/scan-workspace-delete");
  assert.equal(body.task.httpRequest.oidcToken.audience,"https://worker.example");
  assert.equal(JSON.parse(atob(body.task.httpRequest.body)).attempt_count,2);
  assert.match(body.task.name,/standard150-cleanup-scan_123-a2$/);
  for(const status of [200,409]) {
    const pending=await ensureWorkspaceCleanup(run,{env:cleanupEnv,tokenImpl:async()=>"token",fetchImpl:async()=>new Response("",{status})});
    assert.equal(pending.complete,false);
  }
  await assert.rejects(()=>ensureWorkspaceCleanup(run,{env:()=>""}),/not_configured/);
  await assert.rejects(()=>ensureWorkspaceCleanup(run,{env:cleanupEnv,tokenImpl:async()=>"token",fetchImpl:async()=>new Response("",{status:503})}),/enqueue_failed/);
  assert.equal((await ensureWorkspaceCleanup({...run,workspace_cleanup_state:"complete"})).complete,true);
});

test("first screen ranks authenticated page-importance priority ahead of canonical rank",()=>{
  const fix=(fix_id,canonical_action_rank,score)=>({fix_id,canonical_action_rank,root_cause_id:fix_id,stage3_priority_factors:{priority_factor_score:score}});
  assert.deepEqual(topFixIds([fix("low",1,0.1),fix("high",2,0.9),fix("medium",3,0.5),fix("higher",4,0.8)]),["high","higher","medium"]);
});

test("gateway-only workspace cleanup uses the existing drain queue and independently verified HMAC",async()=>{
  const {createHmac}=await import("node:crypto");
  const key="local-cleanup-signing-key";
  let calls=0;
  const result=await ensureWorkspaceCleanup(run,{env:name=>name==="SCAN_DISPATCH_GATEWAY_URL"?"https://gateway.example":name==="SCAN_EVIDENCE_SIGNING_KEY"?key:name==="GCP_SERVICE_ACCOUNT_KEY"?"":cleanupEnv(name),fetchImpl:async(url,init)=>{
    calls++;assert.equal(url,"https://gateway.example/dispatch");
    const derived=createHmac("sha256",key).update("fixlist-dispatch-gateway-v1").digest();
    const expected=createHmac("sha256",derived).update(`${init.headers["x-fixlist-timestamp"]}\n${init.body}`).digest("hex");
    assert.equal(init.headers["x-fixlist-signature"],expected);
    const body=JSON.parse(init.body);assert.equal(body.queue_path,cleanupEnv("SCAN_DRAIN_QUEUE_PATH"));
    assert.equal(JSON.parse(atob(body.task.httpRequest.body)).workspace_cleanup,true);
    return Response.json({success:true});
  }});
  assert.equal(result.complete,false);assert.equal(calls,1);
});

test("true affected counts and qualified template estimates survive writer/readback/customer/preview seals",async()=>{
  const {repairImpactFields}=await import("../../base44/functions/persistDurableScanAuthorityV9/repairImpact.js");
  const preview=await import("../../base44/functions/persistDurableScanAuthorityV9/customerPreviewSeal.js");
  const urls=Array.from({length:150},(_,i)=>`https://example.com/products/${i}`);
  const estimate={route_pattern:"/products/:slug",observed_affected_count:12,checked_sample_count:12,inventory_count:1560,estimated_affected_page_count:1560,is_extrapolation:true,qualification:"Observed on 12 of 12 checked pages; 1560 found. Template impact is an estimate."};
  const args=snapshotArgs(large);
  args.review.recommendations=[{fix_id:"missing_title",rule:"missing_title",issue_title:"Add product titles",priority:"high",affected_pages:urls,page_count:400,affected_page_count:400,affected_page_count_is_lower_bound:true,template_impact_estimates:[estimate],who_can_do_this:"you"}];
  const snapshot=buildAuthoritySnapshot(args);
  const persisted=authorityRowsFromSnapshot(snapshot,{fixListId:"list_123",ownerUserId:"owner_123"});
  const rows={run:{...persisted.scanRun,id:"scan_123",project_id:"project_123"},fixList:{...persisted.fixList,id:"list_123"},fixItems:persisted.fixItems,userId:"owner_123"};
  assert.deepEqual(buildPersistedAuthoritySnapshot(rows),snapshot);
  assert.deepEqual(authoritySnapshotFromRows(rows),snapshot);
  const projection=buildCustomerProjection({...rows,fullAccess:true,authorityVerified:true});
  const fix=projection.fixItems[0];assert.equal(fix.affected_page_count,400);assert.equal(fix.affected_page_count_is_lower_bound,true);assert.deepEqual(fix.template_impact_estimates,[estimate]);assert.equal(fix.affected_pages.length,150);
  const payload=preview.buildCustomerPreviewPayload({...rows,ownerUserId:"owner_123",fullAuthorityProof:"a".repeat(64)});
  assert.equal(payload.fixItems[0].affected_page_count,400);assert.equal(payload.fixItems[0].affected_pages,undefined);assert.equal(payload.fixItems[0].template_impact_estimates[0].is_extrapolation,true);
  const proof=await createAuthoritySeal(snapshot,"count-key",webcrypto);
  const tampered=structuredClone(rows);tampered.fixItems[0].affected_page_count=401;
  assert.equal(await verifyAuthoritySeal(authoritySnapshotFromRows(tampered),"count-key",proof,webcrypto),false);
  assert.throws(()=>repairImpactFields({...args.review.recommendations[0],template_impact_estimates:[{...estimate,is_extrapolation:false}]}));
  assert.throws(()=>repairImpactFields({affected_page_count:501}));
  assert.throws(()=>repairImpactFields({affected_page_count_is_lower_bound:true}));
});

test("stalled staged evidence with zero fixes persists a truthful limited snapshot and reads back identically",async()=>{
  const writer=await import("../../base44/functions/persistLimitedScanResultV9/limitedResultIntegrity.js");
  const reader=await import("../../base44/functions/getCustomerScanResultV9/limitedResultIntegrity.js");
  const args={identity:{scan_id:"scan_123",project_id:"project_123",owner_user_id:"owner_123",request_id:"request_123",attempt_count:1,normalized_domain:"example.com"},scan:{...large,submitted_url:"https://example.com/",pages_crawled:50,pages_found:500,scan_coverage:{urls_attempted:50,usable_html_pages:50,verified_http_failures:0,access_unverified_pages:0,non_html_resources:0,unique_retained_destinations:50}},review:{recommendations:[],coverage_state:"limited_coverage",score_is_provisional:true,release_gate_eligible:false,scan_status:"limited"},now:"2026-11-11T12:00:00Z"};
  const snapshot=writer.buildLimitedResultSnapshot(args);
  assert.equal(snapshot.eligible_for_limited_result,true);assert.match(snapshot.scan.limitation,/incomplete result/);assert.equal(snapshot.scan.release_gate_eligible,false);
  const stored=writer.limitedRowsFromSnapshot(snapshot,{fixListId:"list_123",proof:"a".repeat(64)});
  const rebuilt=reader.buildLimitedResultSnapshot({...args,scan:stored.scanRun,review:{...stored.scanRun,...stored.fixList,recommendations:[]}});
  assert.deepEqual(rebuilt,snapshot);
  const proof=await writer.createLimitedResultProof(snapshot,"partial-key",webcrypto);
  assert.equal(await reader.verifyLimitedResultProof(rebuilt,"partial-key",proof,webcrypto),true);
  for (const scan of [{...args.scan,...standard},{...args.scan,scan_coverage:{...args.scan.scan_coverage,usable_html_pages:0}},{...args.scan,pages_crawled:0}]) assert.equal(writer.buildLimitedResultSnapshot({...args,scan}).eligible_for_limited_result,false);
});

async function controlHarness(recordOverrides = {}) {
  const ts = (await import("typescript")).default;
  const control = await import("../../base44/functions/durableScanWorkerControlV9/authoritySeal.js");
  const release = await import("../../base44/functions/durableScanWorkerControlV9/generatedReleaseContract.js");
  const limits = await import("../../base44/functions/durableScanWorkerControlV9/scanLimits.js");
  const reconciliation = await import("../../base44/functions/durableScanWorkerControlV9/reconciliation.js");
  const signedKey="control-test-key";
  const record={...large,id:"scan_123",project_id:"project_123",owner_user_id:"owner_123",request_id:"request_123",idempotency_key:"request_123",attempt_count:2,status:"crawling",website_url:"https://example.com/",...recordOverrides};
  const updates=[];
  const entities={ScanRun:{get:async()=>structuredClone(record),update:async(_,fields)=>{updates.push(fields);Object.assign(record,fields);}},BusinessProject:{get:async()=>({id:"project_123",owner_user_id:"owner_123",website_url:"https://example.com/"})}};
  const client=()=>({asServiceRole:{entities}});
  let handler;
  const deno={serve:fn=>{handler=fn;},env:{get:()=>""}};
  const source=ts.transpileModule(readFileSync("base44/functions/durableScanWorkerControlV9/entry.ts","utf8"),{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText.replace(/^import[\s\S]*?;\s*$/gm,"");
  new Function("createClientFromRequest","secrets","verifyAuthoritySeal","progressFields","RELEASE_FINGERPRINT","FUNCTION_BUILD_ID","Deno","releaseExactTerminalAdmission",source)(client,{get:()=>signedKey},control.verifyAuthoritySeal,limits.progressFields,release.RELEASE_FINGERPRINT,"test-build",deno,reconciliation.releaseExactTerminalAdmission);
  const identity={scan_id:record.id,project_id:record.project_id,owner_user_id:record.owner_user_id,request_id:record.request_id,idempotency_key:record.idempotency_key,attempt_count:2,normalized_domain:"example.com"};
  return {updates,record,invoke:async({action="progress",progress={pages_crawled:50,pages_planned:500,batch_committed:0},alter=()=>{},identityOverride={}}={})=>{
    const document={version:"durable_standard150_control_v1",action,scan_id:record.id,identity:{...identity,...identityOverride},failure:null,...(action==="progress"?{progress}:{})};
    const proof=await createAuthoritySeal(document,signedKey,webcrypto);
    const body={...document,proof};alter(body);
    const response=await handler(new Request("https://control.example",{method:"POST",headers:{"X-FixList-Worker":"scan_job_worker_v1_cloud_tasks"},body:JSON.stringify(body)}));
    return {status:response.status,body:await response.json()};
  }};
}

test("actual V9 control handler authenticates progress, persists batch heartbeat, and fences superseded/terminal rows",async()=>{
  const live=await controlHarness();const result=await live.invoke();
  assert.equal(result.status,200);assert.equal(live.record.pages_crawled,50);assert.equal(live.record.last_committed_batch,0);assert.ok(live.record.worker_heartbeat_at);
  const tampered=await controlHarness();assert.equal((await tampered.invoke({alter:body=>body.progress.pages_crawled=99})).status,409);assert.equal(tampered.updates.length,0);
  const old=await controlHarness();assert.equal((await old.invoke({identityOverride:{attempt_count:1}})).status,409);assert.equal(old.updates.length,0);
  const terminal=await controlHarness({status:"complete",admission_release_state:"released"});assert.equal((await terminal.invoke()).status,200);assert.equal(terminal.updates.length,0);
  const oversized=await controlHarness();assert.equal((await oversized.invoke({progress:{pages_crawled:501,pages_planned:500}})).status,400);assert.equal(oversized.updates.length,0);
  const activeCleanup=await controlHarness();assert.equal((await activeCleanup.invoke({action:"workspace_deleted"})).status,409);
  const finishedCleanup=await controlHarness({status:"limited"});assert.equal((await finishedCleanup.invoke({action:"workspace_deleted"})).status,200);assert.equal(finishedCleanup.record.workspace_cleanup_state,"complete");
});

test("V9 preserves explicitly unknown reach denominators through strict Stage3 publication and rejects false known claims",async()=>{
  const {spawnSync}=await import("node:child_process");
  const emitted=spawnSync("python",["tests/helpers/emitStage3SignedCompletion.py"],{encoding:"utf8"});
  assert.equal(emitted.status,0,emitted.stderr);
  const {envelope:body}=JSON.parse(emitted.stdout);
  const options={scan:body.scan,review:body.review,identity:body.identity,userId:body.identity.owner_user_id,now:"2026-11-11T12:00:00.000Z",identityVersion:PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION};
  const unknown={reach:null,reach_state:"unknown",reach_affected_indexable:0,reach_observed_indexable_family:null,priority_factor_score:null,score_state:"unknown"};
  for(const fix of body.review.canonical_repairs) Object.assign(fix.stage3_priority_factors,unknown);
  for(const fix of body.review.stage3_handoff_v2_source.fixes) Object.assign(fix.priority_factors,unknown);
  const snapshot=buildAuthoritySnapshot(options);
  const saved=authorityRowsFromSnapshot(snapshot,{fixListId:"list_123",ownerUserId:options.userId});
  const rows={run:{...saved.scanRun,id:body.identity.scan_id,project_id:body.identity.project_id},fixList:{...saved.fixList,id:"list_123"},fixItems:saved.fixItems,userId:options.userId};
  assert.deepEqual(authoritySnapshotFromRows(rows),snapshot);
  const proof=await createAuthoritySeal(snapshot,"unknown-reach-key",webcrypto);
  assert.equal(await verifyAuthoritySeal(authoritySnapshotFromRows(rows),"unknown-reach-key",proof,webcrypto),true);
  for(const patch of [{reach:1,reach_state:"known"},{reach_observed_indexable_family:"unknown"},{priority_factor_score:0,score_state:"known"},{confidence:"1"}]){
    const review=structuredClone(body.review);Object.assign(review.canonical_repairs[0].stage3_priority_factors,patch);
    assert.throws(()=>buildAuthoritySnapshot({...options,review}),/invalid or incomplete/);
  }
});
