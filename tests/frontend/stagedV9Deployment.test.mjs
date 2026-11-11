import assert from "node:assert/strict";
import {chmodSync,cpSync,existsSync,mkdtempSync,mkdirSync,readFileSync,rmSync,writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {spawnSync} from "node:child_process";
import test from "node:test";
const names=["startStandardScanJobV9","durableScanWorkerControlV9","persistDurableScanAuthorityV9","persistLimitedScanResultV9","getCustomerScanResultV9","deleteCustomerScanDataV9"];
const sourceSha="a".repeat(40);
const appId="6a498732ec779dfaaeab0e53";
const publisher="scripts/deploy-base44-staged-functions.sh";
const verifier="scripts/verify-base44-staged-functions.sh";
const text=file=>existsSync(file)?readFileSync(file,"utf8"):"";
function fixture() {
  const root=mkdtempSync(join(tmpdir(),"staged-v9-publish-"));
  const bin=join(root,"bin");mkdirSync(bin);mkdirSync(join(root,"scripts/lib"),{recursive:true});mkdirSync(join(root,"data"));mkdirSync(join(root,"base44/functions"),{recursive:true});
  for(const file of [publisher,verifier,"scripts/base44_release_manifest.mjs","data/base44-function-routes.json","data/beta-crawler-revision.json"]) cpSync(file,join(root,file));
  for(const name of names) cpSync(`base44/functions/${name}`,join(root,"base44/functions",name),{recursive:true});
  const calls=join(root,"calls");const events=join(root,"events");
  writeFileSync(join(root,"scripts/lib/release-source-guard.sh"),`fixlist_require_exact_main() {\n printf 'source-guard\\n' >> "$TEST_EVENTS"\n if [[ "\${TEST_GUARD_FAIL:-}" == yes ]]; then return 2; fi\n FIXLIST_EXACT_SOURCE_SHA="$2"\n}\n`);
  writeFileSync(join(root,"scripts/lib/base44-pinned-cli.sh"),`fixlist_install_base44_cli() { FIXLIST_BASE44_CLI="$TEST_FAKE_CLI"; export FIXLIST_BASE44_CLI; }\nfixlist_require_base44_owner() {\n printf 'owner-check\\n' >> "$TEST_EVENTS"\n [[ "\${TEST_OWNER_FAIL:-}" != yes ]]\n}\n`);
  writeFileSync(join(root,"scripts/generate_release_contracts.mjs"),`import crypto from 'node:crypto';\nimport fs from 'node:fs';\nfs.appendFileSync(process.env.TEST_EVENTS,'generator:'+process.argv[2]+'\\n');\nif(process.argv[2]==='--build-id')process.stdout.write(crypto.createHash('sha256').update(process.argv[3]).digest('hex')+'\\n');\nif(process.argv[2]==='--activation-id')process.stdout.write('staged-'+process.argv[3]+'\\n');\n`);
  const cli=join(bin,"base44");
  writeFileSync(cli,`#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' "$*" >> "$TEST_CLI_CALLS"\n[[ "$1" == --app-id && "$2" == ${appId} && "$3" == functions ]] || exit 9\ncase "$4" in\n deploy) [[ "\${TEST_DEPLOY_FAIL:-}" != yes ]] ;;\n pull)\n  name="$5"\n  [[ "\${TEST_OMIT_PULL:-}" != "$name" ]] || exit 0\n  mkdir -p base44/functions\n  cp -R "$TEST_PACKAGES_ROOT/$name" "base44/functions/$name"\n  if [[ "\${TEST_TAMPER_PULL:-}" == "$name" ]]; then printf '\\n// changed deployed bytes\\n' >> "base44/functions/$name/entry.ts"; fi\n  ;;\n *) exit 10;;\nesac\n`);chmodSync(cli,0o755);
  const curl=join(bin,"curl");
  writeFileSync(curl,`#!${process.execPath}\nconst fs=require('node:fs');const crypto=require('node:crypto');\nconst args=process.argv.slice(2);const name=args.at(-1).split('/').at(-1);\nfs.appendFileSync(process.env.TEST_EVENTS,'probe:'+name+'\\n');\nconst body={build_id:crypto.createHash('sha256').update(name).digest('hex'),runtime_activation_id:'staged-'+name,unexpected_secret:'do-not-copy'};\nif(process.env.TEST_PROBE_MODE==='stale')body.build_id='f'.repeat(64);\nif(process.env.TEST_PROBE_MODE==='activation')body.runtime_activation_id='old-activation';\nfs.writeFileSync(args[args.indexOf('-o')+1],process.env.TEST_PROBE_MODE==='malformed'?'not-json':JSON.stringify(body));\nprocess.stdout.write(process.env.TEST_PROBE_MODE==='success200'?'200':process.env.TEST_PROBE_MODE==='redirect'?'302':'405');\n`);chmodSync(curl,0o755);
  const readiness=join(tmpdir(),`${root.split('/').at(-1)}-readiness.json`);
  const run=(extra={})=>spawnSync("bash",[join(root,publisher)],{cwd:root,encoding:"utf8",env:{...process.env,PATH:`${bin}:${process.env.PATH}`,SOURCE_SHA:sourceSha,CONFIRM:`PUBLISH-BASE44-STAGED-V9:${sourceSha}`,BASE44_APP_ID:appId,BASE44_EXPECTED_OWNER:"owner@example.com",BASE44_API_KEY:"",READINESS_OUTPUT:readiness,PROBE_ATTEMPTS:"1",PROBE_DELAY_SECONDS:"0",TEST_CLI_CALLS:calls,TEST_EVENTS:events,TEST_FAKE_CLI:cli,TEST_PACKAGES_ROOT:join(root,"base44/functions"),...extra}});
  return {root,calls,events,readiness,run,cleanup(){rmSync(root,{recursive:true,force:true});rmSync(readiness,{force:true});}};
}

test("isolated V9 publisher deploys six scoped names, fresh-pulls every package, and issues bounded readiness",()=>{
  const f=fixture();try{
    const result=f.run();assert.equal(result.status,0,result.stderr);
    const calls=text(f.calls).trim().split('\n');assert.equal(calls.length,7);assert.equal(calls[0],`--app-id ${appId} functions deploy ${names.join(' ')}`);
    for(const [index,name] of names.entries())assert.equal(calls[index+1],`--app-id ${appId} functions pull ${name}`);
    assert.doesNotMatch(text(f.calls),/V8|secrets|entities|site|--force/);
    const events=text(f.events);assert.ok(events.indexOf('source-guard')<events.indexOf('owner-check'));assert.match(events,/generator:--check/);
    const readiness=JSON.parse(text(f.readiness));assert.equal(readiness.source_sha,sourceSha);assert.equal(readiness.app_id,appId);assert.match(readiness.candidate_fingerprint,/^[0-9a-f]{16}$/);assert.equal(readiness.production_activation,false);assert.equal(readiness.package_comparison,'matched');assert.equal(readiness.runtime_probe,'matched');assert.deepEqual(readiness.functions.map(row=>row.name),names);
    assert.ok(readiness.functions.every(row=>/^[a-f0-9]{64}$/.test(row.package_digest)&&/^[a-f0-9]{64}$/.test(row.build_id)&&row.http_status===405));assert.doesNotMatch(text(f.readiness),/unexpected_secret|do-not-copy/);
    assert.match(result.stdout,/BASE44_STAGED_V9_CANDIDATE_VERIFIED/);
  }finally{f.cleanup();}
});

for(const [label,extra] of Object.entries({source_guard:{TEST_GUARD_FAIL:'yes'},owner:{TEST_OWNER_FAIL:'yes'},wrong_app:{BASE44_APP_ID:'wrong-app'},missing_sha:{SOURCE_SHA:''},confirmation:{CONFIRM:sourceSha}}))test(`V9 publication fails before deploy when ${label} is invalid`,()=>{
  const f=fixture();try{const result=f.run(extra);assert.notEqual(result.status,0);assert.equal(text(f.calls),'');assert.equal(existsSync(f.readiness),false);}finally{f.cleanup();}
});
for(const [label,extra] of Object.entries({deploy:{TEST_DEPLOY_FAIL:'yes'},missing_pull:{TEST_OMIT_PULL:names[0]},changed_pull:{TEST_TAMPER_PULL:names[0]},stale_runtime:{TEST_PROBE_MODE:'stale'},stale_activation:{TEST_PROBE_MODE:'activation'},malformed_runtime:{TEST_PROBE_MODE:'malformed'},http200:{TEST_PROBE_MODE:'success200'},redirect:{TEST_PROBE_MODE:'redirect'}}))test(`V9 ${label} failure suppresses readiness`,()=>{
  const f=fixture();try{const result=f.run(extra);assert.notEqual(result.status,0);assert.equal(existsSync(f.readiness),false);assert.doesNotMatch(result.stdout,/BASE44_STAGED_V9_CANDIDATE_VERIFIED/);}finally{f.cleanup();}
});

test("V9 candidate scripts keep production promotion and global authority controls outside their mutation surface",()=>{
  const source=text(publisher);assert.match(source,/fixlist_require_exact_main/);assert.match(source,/fixlist_require_base44_owner/);assert.match(source,/functions deploy "\$\{FUNCTIONS\[@\]\}"/);assert.match(source,/functions pull "\$name"/);
  assert.doesNotMatch(source,/fixlist_set_base44_release_source_sha|secrets set|site deploy|entities push|functions deploy --force|assert_standard150_promotion_record/);
  assert.match(text("scripts/deploy-base44-beta-functions.sh"),/assert_standard150_promotion_record/);
  assert.match(text(verifier),/--proto '=https'/);assert.doesNotMatch(text(verifier),/curl[^\n]* -L/);
});

for(const mode of ["v8_alias","already_active","missing_candidate"] )test(`V9 candidate isolation refuses ${mode} before any CLI mutation`,()=>{
  const f=fixture();try{
    const path=join(f.root,"data/base44-function-routes.json");const record=JSON.parse(text(path));
    if(mode==="v8_alias")record.candidate_routes.v9.startStandardScanJob="startStandardScanJobV8";
    if(mode==="already_active")record.routes.startStandardScanJob="startStandardScanJobV9";
    if(mode==="missing_candidate")delete record.candidate_routes.v9;
    writeFileSync(path,JSON.stringify(record));
    const result=f.run();assert.notEqual(result.status,0);assert.equal(text(f.calls),"");assert.equal(existsSync(f.readiness),false);
  }finally{f.cleanup();}
});

test("existing readiness files are protected before any function is deployed",()=>{
  const f=fixture();try{writeFileSync(f.readiness,"existing evidence\n");const result=f.run();assert.notEqual(result.status,0);assert.equal(text(f.calls),"");assert.equal(text(f.readiness),"existing evidence\n");}finally{f.cleanup();}
});
