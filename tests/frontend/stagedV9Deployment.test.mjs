import assert from "node:assert/strict";
import {chmodSync,cpSync,existsSync,mkdtempSync,mkdirSync,readFileSync,realpathSync,rmSync,writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {spawnSync} from "node:child_process";
import test from "node:test";
import { RELEASE_FUNCTIONS } from "../../scripts/base44_release_manifest.mjs";
import { materializeStagedV9Packages } from "../../scripts/lib/staged-v9-function-packages.mjs";
const names=["startStandardScanJobV9","durableScanWorkerControlV9","persistDurableScanAuthorityV9","persistLimitedScanResultV9","getCustomerScanResultV9","deleteCustomerScanDataV9"];
const routeManifest="data/generated-staged-v9-routes.json";
const routes=JSON.parse(readFileSync(routeManifest,"utf8")).functions;
const aliases=names.map(name=>routes[name].route_name);
const sourceSha="a".repeat(40);
const appId="6a498732ec779dfaaeab0e53";
const ownerEmail="bright4862@gmail.com";
const ownerId="6a498da58ef5cec1f5cd4486";
const publisher="scripts/deploy-base44-staged-functions.sh";
const sitePublisher="scripts/deploy-base44-beta-site.sh";
const verifier="scripts/verify-base44-staged-functions.sh";
const collector="scripts/collect-base44-staged-observations.sh";
const operatorProbe="fixlistStagedRuntimeControl";
const text=file=>existsSync(file)?readFileSync(file,"utf8"):"";
function fixture({legacyPackages = false} = {}) {
  const fixtureRoot = realpathSync(mkdtempSync(join(tmpdir(), "staged-v9-publish-")));
  const root = join(fixtureRoot, "repo");
  mkdirSync(root);
  const bin=join(root,"bin");mkdirSync(bin);mkdirSync(join(root,"scripts/lib"),{recursive:true});mkdirSync(join(root,"data"));mkdirSync(join(root,"base44/functions"),{recursive:true});
  for(const file of [publisher,sitePublisher,verifier,collector,"scripts/base44_release_manifest.mjs","scripts/materialize-base44-staged-functions.mjs","scripts/lib/staged-v9-function-packages.mjs","scripts/lib/base44-public-routes.mjs","data/base44-function-routes.json","data/beta-crawler-revision.json",routeManifest]) cpSync(file,join(root,file));
  for(const name of [...names, operatorProbe, ...(legacyPackages ? RELEASE_FUNCTIONS : [])]) cpSync(`base44/functions/${name}`,join(root,"base44/functions",name),{recursive:true});
  const remote=join(root,"remote");mkdirSync(remote);
  const temporary = join(fixtureRoot, "tmp");
  mkdirSync(temporary);
  const upstream=join(root,"expected-packages");
  materializeStagedV9Packages(root,upstream);
  const calls=join(root,"calls");const events=join(root,"events");
  writeFileSync(join(root,"scripts/lib/release-source-guard.sh"),`fixlist_require_exact_main() {
 printf 'source-guard\\n' >> "$TEST_EVENTS"
 if [[ "\${TEST_GUARD_FAIL:-}" == yes ]]; then return 2; fi
 FIXLIST_EXACT_SOURCE_SHA="$2"
}
fixlist_require_pinned_checkout() {
 printf 'pinned-source\\n' >> "$TEST_EVENTS"
 [[ "$2" == "$FIXLIST_EXACT_SOURCE_SHA" ]]
}
`);
  writeFileSync(join(root,"scripts/lib/base44-pinned-cli.sh"),`fixlist_install_base44_cli() { FIXLIST_BASE44_CLI="$TEST_FAKE_CLI"; export FIXLIST_BASE44_CLI; }\nfixlist_require_base44_owner() {\n printf 'owner-check\\n' >> "$TEST_EVENTS"\n [[ "\${TEST_OWNER_FAIL:-}" != yes ]]\n}\nfixlist_set_base44_release_source_sha() { printf 'provenance-write\\n' >> "$TEST_EVENTS"; }\n`);
  writeFileSync(join(root,"scripts/verify-base44-functions.sh"),`printf 'site-wrapper-function-check\\n' >> "$TEST_EVENTS"\n`);
  writeFileSync(join(bin,"npm"),`#!/usr/bin/env bash\nprintf 'site-wrapper-build\\n' >> "$TEST_EVENTS"\n`,{mode:0o700});
  writeFileSync(join(root, "scripts/assert_standard150_promotion_record.py"), `import json, os, sys
with open(os.environ['TEST_EVENTS'], 'a') as events:
    events.write('promotion-guard\\n')
with open('data/beta-crawler-revision.json') as source:
    if json.load(source)['status'] != 'frozen_beta' or sys.argv[1:3] != ['--source-sha', '${sourceSha}']:
        sys.exit(2)
`);
  writeFileSync(join(root,"scripts/generate_release_contracts.mjs"),`import crypto from 'node:crypto';\nimport fs from 'node:fs';\nfs.appendFileSync(process.env.TEST_EVENTS,'generator:'+process.argv[2]+'\\n');\nif(process.argv[2]==='--build-id')process.stdout.write(crypto.createHash('sha256').update(process.argv[3]).digest('hex')+'\\n');\nif(process.argv[2]==='--activation-id')process.stdout.write('staged-'+process.argv[3]+'\\n');\n`);
  writeFileSync(join(root,"scripts/base44_staged_schema.mjs"),`import fs from 'node:fs';
const [operation, sourceFlag, source, reportFlag, report] = process.argv.slice(2);
if (operation !== 'verify' || sourceFlag !== '--source-sha' || source !== 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' || reportFlag !== '--report') process.exit(9);
fs.writeFileSync(report, JSON.stringify({action: operation, source_sha: source}), {flag:'wx',mode:0o600});`);
  const fakeReadback=join(bin,"readback");
  writeFileSync(fakeReadback,`#!${process.execPath}
const fs=require('node:fs');
const name='startStandardScanJobV9';
const routes=Object.values(require(process.env.TEST_ROUTE_MANIFEST).functions);
const identity=alias=>routes.find(row=>row.route_name===alias);
const program=fs.readFileSync(0,'utf8');
if (program.includes('BASE44_ACTIVE_V9_INTAKE_DISABLED') || program.includes('BASE44_INDEPENDENT_SCAN_INTAKE_DISABLED')) {
 const mode=process.env.TEST_ACTIVE_INTAKE;
 const identity=routes.find(row=>row.route_name.startsWith(name));
 const base44={
  auth:{me:async()=>({id:mode==='wrong-owner'?'unapproved':"${ownerId}",email:"${ownerEmail}",role:'admin'})},
  functions:{invoke:async(route, body)=>{
   if (route==='${operatorProbe}' && body.action==='status') {
    fs.appendFileSync(process.env.TEST_EVENTS,'independent-intake-probe\\n');
    const closed=process.env.TEST_INDEPENDENT_INTAKE!=='open';
    return {data:{success:true,schema_version:'fixlist_staged_runtime_readback_v1',
     operator_build_id:process.env.TEST_INDEPENDENT_INTAKE==='stale'?'stale':'fixlist-staged-runtime-control-v1',
     intake_gate:closed?'disabled':'enabled',intake_disabled_verified:closed,new_owner_intake_disabled:closed,v9_runtime_attested:false}};
   }
   if (route!==identity.route_name || body.action!=='staged_runtime_status') process.exit(13);
   if (process.env.TEST_REQUIRE_ACTIVE_LAUNCHER==='yes' && !fs.existsSync(process.env.TEST_REMOTE+'/'+route)) process.exit(14);
   fs.appendFileSync(process.env.TEST_EVENTS,'intake-probe:'+route+'\\n');
   return {data:{success:true,schema_version:'fixlist_staged_v9_intake_readback_v1',observed_at:new Date().toISOString(),
    release_fingerprint:process.env.TEST_FINGERPRINT,build_id:mode==='stale-build'?'b'.repeat(64):identity.build_id,
    runtime_activation_id:identity.runtime_activation_id,intake_gate:mode==='open'?'enabled':'disabled'}};
  }},
 };
 const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
 new AsyncFunction('base44',program)(base44).catch(()=>{process.exitCode=12;});
 return;
}
if (program.includes('FIXLIST_V9_NATIVE_GET=')) {
 const mode=process.env.TEST_PROBE_MODE;
 const base44={
  auth:{me:async()=>({id:mode==='wrong_app_owner'?'unapproved':"${ownerId}",email:"${ownerEmail}",role:'admin'})},
  functions:{fetch:async(path,options)=>{
   if (!path.startsWith('/') || options.method!=='GET' || options.redirect!=='error' || options.cache!=='no-store') process.exit(11);
   const name=path.slice(1);
   fs.appendFileSync(process.env.TEST_EVENTS,'native-probe:'+name+'\\n');
   if (!identity(name)) process.exit(13);
   const body={...identity(name),unexpected_secret:'do-not-copy'};
   if(mode==='stale')body.build_id='f'.repeat(64);
   if(mode==='activation')body.runtime_activation_id='old-activation';
   const status=mode==='success200'?200:mode==='redirect'?302:405;
   const url='https://'+(mode==='wrong_host'?'example.test':'getfixlist.base44.app')+'/api/functions/'+name;
   return {status,url,text:async()=>mode==='malformed'?'not-json':JSON.stringify(body)};
  }},
 };
 const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
 new AsyncFunction('base44',program)(base44).catch(()=>{process.exitCode=12;});
 return;
}
const intake=require(process.env.TEST_ROUTE_MANIFEST).functions[name];
if (!program.includes('staged_runtime_status') || !program.includes(intake.route_name)) process.exit(12);
const mode=process.env.TEST_INTAKE_MODE;
const report={schema_version:'fixlist_staged_v9_intake_readback_v1',success:true,observed_at:new Date().toISOString(),
  build_id: mode==='stale' ? 'f'.repeat(64) : intake.build_id,
  runtime_activation_id:intake.runtime_activation_id,release_fingerprint:process.env.TEST_FINGERPRINT,
  configured_pipeline_mode:'staged',pipeline_mode:'staged',staged_owner_cohort_state:'explicit',
  staged_owner_count:1,staged_owner_cohort_sha256:'a'.repeat(64),staged_owner_enabled:true,
  intake_gate:'enabled',admission_gate:'enabled',unexpected_secret:'do-not-copy'};
const line='FIXLIST_V9_INTAKE_READBACK='+JSON.stringify(report);
console.log(line);
if(mode==='duplicate')console.log(line);`);chmodSync(fakeReadback,0o755);
  const fakePull = join(bin, "pull");
  writeFileSync(fakePull, `#!${process.execPath}
const fs = require('node:fs');
const path = require('node:path');
const name = process.argv[2];
const source = name==='${operatorProbe}' ? process.env.TEST_OPERATOR_PACKAGE : path.join(process.env.TEST_PACKAGES_ROOT, name);
const pulled = path.join('base44/functions', name);
const routed = process.env.TEST_FLAT_PULL === 'yes' ? pulled : path.join(pulled, 'base44/functions', name);
fs.mkdirSync(path.dirname(routed), { recursive: true });
fs.cpSync(source, routed, { recursive: true });
const configFile = path.join(routed, 'function.jsonc');
if (routed !== pulled) {
  const config = JSON.parse(fs.readFileSync(configFile, 'utf8'));
  config.entry = 'base44/functions/' + name + '/' + config.entry;
  if (name === process.env.TEST_TAMPER_PULL) {
    if (process.env.TEST_TAMPER_MODE === 'entry') config.entry = 'base44/functions/unrelated/entry.ts';
    if (process.env.TEST_TAMPER_MODE === 'config') config.trigger = 'unexpected';
  }
  fs.unlinkSync(configFile);
  fs.writeFileSync(path.join(pulled, 'function.jsonc'), JSON.stringify(config, null, 2));
} else {
  const config = JSON.parse(fs.readFileSync(configFile, 'utf8'));
  if (name === process.env.TEST_TAMPER_PULL && process.env.TEST_TAMPER_MODE === 'config') config.trigger = 'unexpected';
  fs.writeFileSync(configFile, JSON.stringify(config, null, 2));
}
if (name === process.env.TEST_TAMPER_PULL) {
  const entry = path.join(routed, 'entry.ts');
  switch (process.env.TEST_TAMPER_MODE) {
    case 'entry': case 'config': break;
    case 'missing': fs.unlinkSync(entry); break;
    case 'wrapper': fs.writeFileSync(path.join(pulled, 'base44', 'unexpected.txt'), 'extra'); break;
    case 'extra': fs.writeFileSync(path.join(routed, 'unexpected.js'), 'extra'); break;
    case 'symlink': fs.unlinkSync(entry); fs.symlinkSync(path.join(source, 'entry.ts'), entry); break;
    default: fs.appendFileSync(entry, '\\n// changed deployed bytes\\n');
  }
}
`);
  chmodSync(fakePull, 0o755);
  const cli=join(bin,"base44");
  writeFileSync(cli,`#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "$TEST_CLI_CALLS"
[[ "$1" == --app-id && "$2" == ${appId} ]] || exit 9
if [[ "$3" == exec && "$4" == --data-env && "$5" == prod ]]; then exec "$TEST_FAKE_READBACK"; fi
if [[ "\${TEST_INTERRUPT_SITE:-}" == yes ]]; then
  if [[ "$3 $4" == 'functions deploy' && "$5" == *V8 ]]; then exit 0; fi
  if [[ "$3 $4" == 'site deploy' ]]; then
    [[ "$(ps -p "$PPID" -o command=)" == *"$TEST_SITE_WRAPPER"* ]] || exit 15
    for alias in ${aliases.join(" ")}; do rm -f "$TEST_REMOTE/$alias"; done
    printf 'provider-pruned-v9-routes\\n' >> "$TEST_EVENTS"
    kill -KILL "$PPID"
    exit 0
  fi
fi
[[ "$3" == functions && "$#" == 5 ]] || exit 9
name="$5"
case "$4" in
 deploy)
  [[ "\${TEST_DEPLOY_FAIL:-}" != yes && -f "base44/functions/$name/function.jsonc" ]] || exit 9
  [[ ! -e "$TEST_REMOTE/$name" && "\${TEST_PREEXIST:-}" != yes && "\${TEST_PREEXIST_ROUTE:-}" != "$name" ]] || exit 10
  diff -r "base44/functions/$name" "$TEST_PACKAGES_ROOT/$name"
  touch "$TEST_REMOTE/$name"
  ;;
 pull)
  [[ "\${TEST_OMIT_PULL:-}" != "$name" ]] || exit 0
  if [[ "\${TEST_PREEXIST:-}" != yes && "\${TEST_PREEXIST_ROUTE:-}" != "$name" && ! -e "$TEST_REMOTE/$name" ]]; then
    printf 'Function "%s" not found on remote\\n' "$name"
    exit 0
  fi
  exec "$TEST_FAKE_PULL" "$name"
  ;;
 *) exit 10;;
esac
`);chmodSync(cli,0o755);
  const curl=join(bin,"curl");
  writeFileSync(curl,`#!${process.execPath}
const fs=require('node:fs');
const args=process.argv.slice(2);
const url=args.at(-1);
const prefix='https://base44.app/api/apps/${appId}/functions/';
if (!url.startsWith(prefix) || args[0]!=='-q' || args.includes('-L')) process.exit(11);
const name=url.slice(prefix.length);
const route=Object.values(require(process.env.TEST_ROUTE_MANIFEST).functions).find(row=>row.route_name===name);
if (!route) process.exit(11);
const output=args[args.indexOf('-o')+1];
if (output==='/dev/null') {
 fs.appendFileSync(process.env.TEST_EVENTS,'collision-check:'+name+'\\n');
 process.stdout.write(process.env.TEST_ORPHAN_ROUTE===name?'405':'404');
 process.exit(0);
}
fs.appendFileSync(process.env.TEST_EVENTS,'anonymous-probe:'+name+'\\n');
const body={...route,unexpected_secret:'do-not-copy'};
if(process.env.TEST_ANONYMOUS_MODE==='down') process.exit(7);
if(process.env.TEST_ANONYMOUS_MODE==='stale') body.build_id='f'.repeat(64);
if(process.env.TEST_ANONYMOUS_MODE==='activation') body.runtime_activation_id='previous';
fs.writeFileSync(output,process.env.TEST_ANONYMOUS_MODE==='malformed'?'not-json':JSON.stringify(body));
process.stdout.write('405');
`);chmodSync(curl,0o755);
  const readiness = join(fixtureRoot, "readiness.json");
  const activeEntry = join(root, 'scripts/active-v9-wrapper.sh');
  writeFileSync(activeEntry, `#!/usr/bin/env bash
set -euo pipefail
source scripts/lib/release-source-guard.sh
fixlist_require_exact_main "$PWD" "$SOURCE_SHA" "$SOURCE_SHA"
python3 scripts/assert_standard150_promotion_record.py --source-sha "$SOURCE_SHA"
source scripts/deploy-base44-staged-functions.sh
fixlist_publish_v9_packages active-preflight
if [[ "\${TEST_RESTORE:-}" == yes ]]; then
  export TEST_GUARD_FAIL=yes
  export READINESS_OUTPUT="$READINESS_OUTPUT.restored"
  fixlist_publish_v9_packages active-restore
fi
`);
  const run=(extra={},args=[],script=publisher)=>spawnSync("bash",[join(root,script),...args],{cwd:root,encoding:"utf8",env:{...process.env,PATH:`${bin}:${process.env.PATH}`,TMPDIR:temporary,SOURCE_SHA:sourceSha,CONFIRM:`PUBLISH-BASE44-STAGED-V9:${sourceSha}`,BASE44_APP_ID:appId,BASE44_EXPECTED_OWNER:ownerEmail,BASE44_API_KEY:"",READINESS_OUTPUT:readiness,PROBE_ATTEMPTS:"1",PROBE_DELAY_SECONDS:"0",TEST_CLI_CALLS:calls,TEST_EVENTS:events,TEST_FAKE_CLI:cli,TEST_FAKE_READBACK:fakeReadback,TEST_FAKE_PULL:fakePull,TEST_FINGERPRINT:JSON.parse(text(join(root,"data/beta-crawler-revision.json"))).fingerprint,TEST_PACKAGES_ROOT:join(upstream,"base44/functions"),TEST_ROUTE_MANIFEST:join(root,routeManifest),TEST_REMOTE:remote,TEST_OPERATOR_PACKAGE:join(root,"base44/functions",operatorProbe),TEST_SITE_WRAPPER:join(root,sitePublisher),...extra}});
  return {root,remote,calls,events,readiness,run,cleanup(){rmSync(fixtureRoot,{recursive:true,force:true});}};
}

const pullCall=route=>`--app-id ${appId} functions pull ${route}`;
const deployCall=route=>`--app-id ${appId} functions deploy ${route}`;
const execCall=`--app-id ${appId} exec --data-env prod`;

test("isolated V9 publisher checks six aliases, deploys each one individually, and proves both runtime lanes",()=>{
  const f=fixture();try{
    const result=f.run({TEST_FLAT_PULL:"yes"});assert.equal(result.status,0,result.stderr);
    const calls=text(f.calls).trim().split('\n');
    assert.deepEqual(calls,[...aliases.map(pullCall),...aliases.flatMap(route=>[pullCall(route),deployCall(route),pullCall(route)]),execCall]);
    assert.doesNotMatch(text(f.calls),/V8|secrets|entities|site|--force/);
    const events=text(f.events);assert.ok(events.indexOf('source-guard')<events.indexOf('owner-check'));assert.match(events,/generator:--check/);
    const readiness=JSON.parse(text(f.readiness));assert.equal(readiness.source_sha,sourceSha);assert.equal(readiness.app_id,appId);assert.match(readiness.candidate_fingerprint,/^[0-9a-f]{16}$/);assert.equal(readiness.production_activation,false);assert.equal(readiness.package_comparison,'matched');assert.equal(readiness.runtime_probe,'matched');assert.deepEqual(readiness.functions.map(row=>row.name),names);
    assert.equal(readiness.schema_version,"fixlist_staged_v9_readiness_v2");
    assert.deepEqual(readiness.functions,names.map(name=>({name,...routes[name],http_status:405})));
    assert.doesNotMatch(text(f.readiness),/unexpected_secret|do-not-copy/);
    assert.equal(readiness.runtime_probe_transport,"base44_native_authenticated_sdk_get");
    assert.equal(readiness.worker_signed_post_runtime_verified,false);
    assert.equal(readiness.anonymous_probe.transport,"base44_legacy_anonymous_get");
    assert.deepEqual(readiness.anonymous_probe.functions,names.map(name=>{
      const {route_name,build_id,runtime_activation_id}=routes[name];
      return {name,route_name,build_id,runtime_activation_id,http_status:405,state:"matched"};
    }));
    assert.match(result.stdout,/BASE44_STAGED_V9_CANDIDATE_VERIFIED/);
  }finally{f.cleanup();}
});

test("known exact aliases are idempotent and can be verified without republishing",()=>{
  const f=fixture();try{
    const result=f.run({TEST_PREEXIST:"yes"});assert.equal(result.status,0,result.stderr);
    assert.deepEqual(text(f.calls).trim().split("\n"),[...aliases.map(pullCall),execCall]);
    assert.doesNotMatch(text(f.events),/collision-check:/);
    assert.equal(JSON.parse(text(f.readiness)).functions.length,6);
  }finally{f.cleanup();}
});

test("pilot recovery can prove the pinned runtime after main advances without publishing a missing route", t => {
  const script = "scripts/after-pilot-upload.sh";
  for (const packagesPresent of [true, false]) {
    const f = fixture();
    t.after(f.cleanup);
    writeFileSync(join(f.root, script), [
      "set -euo pipefail",
      'export FIXLIST_EXACT_SOURCE_SHA="$SOURCE_SHA"',
      'export CONFIRM="VERIFY-PINNED-BASE44-STAGED-V9:$SOURCE_SHA"',
      "source scripts/deploy-base44-staged-functions.sh",
      "fixlist_publish_v9_packages verify-pinned",
    ].join("\n"));
    const result = f.run({
      TEST_GUARD_FAIL: "yes",
      TEST_PREEXIST: packagesPresent ? "yes" : "no",
      TEST_FLAT_PULL: "yes",
    }, [], script);
    assert.doesNotMatch(text(f.events), /source-guard/);
    assert.match(text(f.events), /pinned-source/);
    assert.doesNotMatch(text(f.calls), /functions deploy/);
    if (packagesPresent) {
      assert.equal(result.status, 0, result.stderr);
      assert.equal(JSON.parse(text(f.readiness)).source_sha, sourceSha);
      assert.deepEqual(text(f.calls).trim().split("\n"), [...aliases.map(pullCall), execCall]);
    } else {
      assert.notEqual(result.status, 0);
      assert.match(result.stderr, /V9 deployed readback is missing/);
      assert.equal(existsSync(f.readiness), false);
      assert.equal(text(f.calls).trim(), pullCall(aliases[0]));
    }
  }
});

test("V9 flat pull permits only the pinned CLI's omission of the config newline",()=>{
  const f=fixture();try{
    const result=f.run({TEST_FLAT_PULL:"yes",TEST_PREEXIST:"yes",TEST_TAMPER_PULL:aliases[0],TEST_TAMPER_MODE:"config"});
    assert.notEqual(result.status,0);
    assert.match(result.stderr,/file bytes differ for function.jsonc/);
    assert.equal(existsSync(f.readiness),false);
    assert.doesNotMatch(text(f.calls),/functions deploy/);
  }finally{f.cleanup();}
});

for(const [label,extra] of Object.entries({source_guard:{TEST_GUARD_FAIL:'yes'},owner:{TEST_OWNER_FAIL:'yes'},wrong_app:{BASE44_APP_ID:'wrong-app'},missing_sha:{SOURCE_SHA:''},confirmation:{CONFIRM:sourceSha},workspace_key:{BASE44_API_KEY:"unused-workspace-key"}}))test(`V9 publication fails before deploy when ${label} is invalid`,()=>{
  const f=fixture();try{const result=f.run(extra);assert.notEqual(result.status,0);assert.equal(text(f.calls),'');assert.equal(existsSync(f.readiness),false);}finally{f.cleanup();}
});
for(const [label,extra] of Object.entries({deploy:{TEST_DEPLOY_FAIL:'yes'},missing_pull:{TEST_OMIT_PULL:aliases[0]},changed_pull:{TEST_TAMPER_PULL:aliases[0]},stale_runtime:{TEST_PROBE_MODE:'stale'},stale_activation:{TEST_PROBE_MODE:'activation'},malformed_runtime:{TEST_PROBE_MODE:'malformed'},http200:{TEST_PROBE_MODE:'success200'},redirect:{TEST_PROBE_MODE:'redirect'},wrong_native_host:{TEST_PROBE_MODE:'wrong_host'},wrong_app_owner:{TEST_PROBE_MODE:'wrong_app_owner'}}))test(`V9 ${label} failure suppresses readiness`,()=>{
  const f=fixture();try{const result=f.run(extra);assert.notEqual(result.status,0);assert.equal(existsSync(f.readiness),false);assert.doesNotMatch(result.stdout,/BASE44_STAGED_V9_CANDIDATE_VERIFIED/);}finally{f.cleanup();}
});

for(const [label,extra] of Object.entries({registered:{TEST_PREEXIST_ROUTE:aliases[5],TEST_TAMPER_PULL:aliases[5]},public:{TEST_ORPHAN_ROUTE:aliases[5]}}))test(`V9 preflights the whole cohort before writing any alias on ${label} collision`,()=>{
  const f=fixture();try{
    const result=f.run(extra);assert.notEqual(result.status,0);
    assert.deepEqual(text(f.calls).trim().split("\n"),aliases.map(pullCall));
    assert.equal(existsSync(f.readiness),false);
  }finally{f.cleanup();}
});

for (const mode of ["stale","activation","malformed","down"]) {
  test(`V9 rejects ${mode} anonymous probes despite exact native builds`, () => {
    const f = fixture();
    try {
      const result = f.run({ TEST_ANONYMOUS_MODE: mode, TEST_PREEXIST:"yes" });
      assert.notEqual(result.status, 0);
      assert.match(result.stderr, /V9 external runtime identities could not be verified/);
      assert.equal(existsSync(f.readiness),false);
      assert.deepEqual(text(f.calls).trim().split("\n"),[...aliases.map(pullCall),execCall]);
    } finally { f.cleanup(); }
  });
}

for (const mode of ["entry", "config", "missing", "wrapper", "extra", "symlink"]) {
  test(`V9 rejects ${mode} drift in the pinned CLI's nested pull layout`, () => {
    const f = fixture();
    try {
      const result = f.run({ TEST_TAMPER_PULL: aliases[0], TEST_TAMPER_MODE: mode, TEST_PREEXIST:"yes" });
      assert.notEqual(result.status, 0);
      assert.match(result.stderr, /V9 deployed package differs: startStandardScanJobV9/);
      assert.equal(existsSync(f.readiness), false);
      assert.doesNotMatch(text(f.events), /probe:/);
      assert.doesNotMatch(text(f.calls), /functions deploy/);
    } finally {
      f.cleanup();
    }
  });
}

test("V9 candidate scripts keep production promotion and global authority controls outside their mutation surface",()=>{
  const source=text(publisher);assert.match(source,/fixlist_require_exact_main/);assert.match(source,/fixlist_require_base44_owner/);assert.match(source,/functions deploy "\$route"/);assert.match(source,/functions pull "\$route"/);
  assert.doesNotMatch(source,/fixlist_set_base44_release_source_sha|secrets set|site deploy|entities push|functions deploy --force|functions delete/);
  assert.match(source,/publish\|verify\|recover-active\) fixlist_publish_v9_packages/);
  assert.match(text("scripts/deploy-base44-beta-functions.sh"),/assert_standard150_promotion_record/);
  assert.match(text(verifier),/--proto '=https'/);assert.doesNotMatch(text(verifier),/curl[^\n]* -L/);
});

function selectActiveV9(fixtureRoot) {
  const file = join(fixtureRoot, "data/base44-function-routes.json");
  const manifest = JSON.parse(text(file));
  manifest.generation = "v9";
  manifest.historical_routes.v8 = manifest.routes;
  manifest.routes = manifest.candidate_routes.v9;
  delete manifest.candidate_routes.v9;
  writeFileSync(file, JSON.stringify(manifest));
}

function freezeActiveV9(fixtureRoot) {
  selectActiveV9(fixtureRoot);
  const file = join(fixtureRoot, "data/beta-crawler-revision.json");
  const record = JSON.parse(text(file));
  writeFileSync(file, JSON.stringify({ ...record, status: "frozen_beta" }));
}

test("packages-only recovery restores the missing launcher after the actual site wrapper is interrupted", (t) => {
  const f = fixture({legacyPackages: true});
  t.after(f.cleanup);
  freezeActiveV9(f.root);
  for (const route of [...aliases, operatorProbe]) writeFileSync(join(f.remote, route), "");
  const interrupted = f.run({ CONFIRM: sourceSha, TEST_INTERRUPT_SITE: "yes", TEST_REQUIRE_ACTIVE_LAUNCHER: "yes" }, [], sitePublisher);
  assert.equal(interrupted.signal, "SIGKILL", interrupted.stderr);
  assert.match(text(f.events), /provider-pruned-v9-routes/);
  for (const route of aliases) assert.equal(existsSync(join(f.remote, route)), false);
  assert.equal(existsSync(join(f.remote, operatorProbe)), true);

  const callsBefore = text(f.calls).length;
  const eventsBefore = text(f.events).length;
  const recovered = f.run({ CONFIRM: `RECOVER-BASE44-ACTIVE-V9:${sourceSha}`, TEST_REQUIRE_ACTIVE_LAUNCHER: "yes" }, ["recover-active"]);
  assert.equal(recovered.status, 0, recovered.stderr);
  assert.match(recovered.stdout, /BASE44_INDEPENDENT_SCAN_INTAKE_DISABLED[\s\S]*BASE44_ACTIVE_V9_PACKAGES_RECOVERED/);
  assert.deepEqual(text(f.calls).slice(callsBefore).trim().split("\n"), [
    ...aliases.map(pullCall), pullCall(operatorProbe), execCall,
    ...aliases.flatMap(route => [pullCall(route), deployCall(route), pullCall(route)]), execCall, execCall,
  ]);
  const events = text(f.events).slice(eventsBefore);
  assert.match(events, /independent-intake-probe[\s\S]*intake-probe:/);
  assert.doesNotMatch(events, /provenance-write|site-wrapper|provider-pruned/);
  for (const route of aliases) assert.equal(existsSync(join(f.remote, route)), true);
  assert.deepEqual(JSON.parse(text(f.readiness)).functions.map(row => row.route_name), aliases);
});

for (const [title, env, probePresent] of [
  ["missing independent probe", {}, false],
  ["different independent probe bytes", { TEST_TAMPER_PULL: operatorProbe }, true],
  ["open intake", { TEST_INDEPENDENT_INTAKE: "open" }, true],
  ["stale independent probe", { TEST_INDEPENDENT_INTAKE: "stale" }, true],
  ["public alias collision", { TEST_ORPHAN_ROUTE: aliases[5] }, true],
  ["wrong host", { BASE44_FUNCTION_ORIGIN: "https://elsewhere.invalid" }, true],
  ["source outside current main", { TEST_GUARD_FAIL: "yes" }, true],
]) {
  test(`restart recovery stops before any package write with ${title}`, (t) => {
    const f = fixture();
    t.after(f.cleanup);
    freezeActiveV9(f.root);
    if (probePresent) writeFileSync(join(f.remote, operatorProbe), "");
    const result = f.run({ ...env, CONFIRM: `RECOVER-BASE44-ACTIVE-V9:${sourceSha}` }, ["recover-active"]);
    assert.notEqual(result.status, 0);
    assert.doesNotMatch(text(f.calls), /functions deploy/);
    assert.equal(existsSync(f.readiness), false);
  });
}

test("restart recovery requires distinct approval and uses the launcher when it still exists", (t) => {
  const f = fixture();
  t.after(f.cleanup);
  freezeActiveV9(f.root);
  for (const route of [...aliases, operatorProbe]) writeFileSync(join(f.remote, route), "");
  const denied = f.run({ CONFIRM: `PUBLISH-BASE44-ACTIVE-V9:${sourceSha}` }, ["recover-active"]);
  assert.notEqual(denied.status, 0);
  assert.equal(text(f.calls), "");
  const open = f.run({ CONFIRM: `RECOVER-BASE44-ACTIVE-V9:${sourceSha}`, TEST_ACTIVE_INTAKE: "open" }, ["recover-active"]);
  assert.notEqual(open.status, 0);
  assert.doesNotMatch(text(f.calls), /functions deploy|functions pull fixlistStagedRuntimeControl/);
  assert.doesNotMatch(text(f.events), /independent-intake-probe/);
  assert.equal(existsSync(f.readiness), false);
});

test("restart recovery withholds readiness if the restored launcher reports open intake", (t) => {
  const f = fixture();
  t.after(f.cleanup);
  freezeActiveV9(f.root);
  writeFileSync(join(f.remote, operatorProbe), "");
  const result = f.run({ CONFIRM: `RECOVER-BASE44-ACTIVE-V9:${sourceSha}`, TEST_ACTIVE_INTAKE: "open" }, ["recover-active"]);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /exact launcher does not attest closed intake/);
  assert.match(text(f.events), /independent-intake-probe[\s\S]*intake-probe:/);
  assert.equal(existsSync(join(f.remote, aliases[0])), true);
  assert.equal(existsSync(f.readiness), false);
  assert.doesNotMatch(result.stdout, /PACKAGES_RECOVERED/);
});

test("active V9 package publication requires frozen accepted source and restores only missing exact aliases", (t) => {
  const f = fixture();
  t.after(f.cleanup);
  selectActiveV9(f.root);
  const confirm = { CONFIRM: `PUBLISH-BASE44-ACTIVE-V9:${sourceSha}` };
  assert.notEqual(f.run(confirm, [], "scripts/active-v9-wrapper.sh").status, 0);
  assert.equal(text(f.calls), "");
  assert.match(text(f.events), /promotion-guard/);

  const revisionPath = join(f.root, "data/beta-crawler-revision.json");
  const revision = JSON.parse(text(revisionPath));
  writeFileSync(revisionPath, JSON.stringify({ ...revision, status: "frozen_beta" }));
  assert.notEqual(f.run().status, 0);
  assert.notEqual(f.run(confirm, ["active-preflight"]).status, 0);
  assert.equal(text(f.calls), "");

  const startEventCount = text(f.events).match(/source-guard/g)?.length ?? 0;
  const result = f.run({ ...confirm, TEST_PREEXIST_ROUTE: aliases[0], TEST_RESTORE: "yes" }, [], "scripts/active-v9-wrapper.sh");
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(text(f.calls).trim().split("\n"), [
    ...aliases.map(pullCall), execCall, ...aliases.slice(1).flatMap(route => [pullCall(route), deployCall(route), pullCall(route)]), execCall,
    ...aliases.map(pullCall), execCall,
  ]);
  assert.equal(text(f.events).match(/source-guard/g)?.length, startEventCount + 1);
  assert.equal(text(f.events).match(/pinned-source/g)?.length, 4);
  assert.match(result.stdout, /BASE44_ACTIVE_V9_PACKAGES_VERIFIED/);
  assert.doesNotMatch(result.stdout, /BASE44_STAGED_V9_CANDIDATE_VERIFIED/);
  assert.deepEqual(JSON.parse(text(f.readiness)).functions.map(row => row.route_name), aliases);
});

for (const [failure, env] of Object.entries({
  api_key: {BASE44_API_KEY: "not-permitted"},
  owner: {TEST_OWNER_FAIL: "yes"},
  collision: {TEST_PREEXIST: "yes", TEST_TAMPER_PULL: aliases[5]},
  wrong_app_owner: {TEST_ACTIVE_INTAKE: "wrong-owner"},
  open: {TEST_ACTIVE_INTAKE: "open"},
  stale_intake: {TEST_ACTIVE_INTAKE: "stale-build"},
})) {
  test(`active V9 preflight refuses ${failure} before alias creation`, (t) => {
    const f = fixture();
    t.after(f.cleanup);
    selectActiveV9(f.root);
    const revisionPath = join(f.root, "data/beta-crawler-revision.json");
    const revision = JSON.parse(text(revisionPath));
    writeFileSync(revisionPath, JSON.stringify({ ...revision, status: "frozen_beta" }));
    const result = f.run({ ...env, CONFIRM: `PUBLISH-BASE44-ACTIVE-V9:${sourceSha}` }, [], "scripts/active-v9-wrapper.sh");
    assert.notEqual(result.status, 0);
    assert.doesNotMatch(text(f.calls), /functions deploy/);
    assert.equal(existsSync(f.readiness), false);
  });
}

test("active V9 rejects a well-shaped but stale generated route before any CLI operation", (t) => {
  const f = fixture();
  t.after(f.cleanup);
  selectActiveV9(f.root);
  const revisionPath = join(f.root, "data/beta-crawler-revision.json");
  const revision = JSON.parse(text(revisionPath));
  writeFileSync(revisionPath, JSON.stringify({ ...revision, status: "frozen_beta" }));
  const generated = join(f.root, routeManifest);
  const record = JSON.parse(text(generated));
  record.functions[names[0]].route_name = `${names[0]}B${"f".repeat(16)}`;
  writeFileSync(generated, JSON.stringify(record));

  const result = f.run({ CONFIRM: `PUBLISH-BASE44-ACTIVE-V9:${sourceSha}` }, [], "scripts/active-v9-wrapper.sh");
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /Generated staged V9 routes differ from package bytes/);
  assert.equal(text(f.calls), "");
});

test("active V9 preflight checks timeout's required options before any CLI operation", (t) => {
  const f = fixture();
  t.after(f.cleanup);
  selectActiveV9(f.root);
  const unsupported = join(f.root, "bin/timeout");
  writeFileSync(unsupported, "#!/usr/bin/env bash\nexit 2\n", { mode: 0o700 });
  const revisionPath = join(f.root, "data/beta-crawler-revision.json");
  const revision = JSON.parse(text(revisionPath));
  writeFileSync(revisionPath, JSON.stringify({ ...revision, status: "frozen_beta" }));
  const result = f.run({ CONFIRM: `PUBLISH-BASE44-ACTIVE-V9:${sourceSha}` }, [], "scripts/active-v9-wrapper.sh");
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /GNU-compatible timeout is required/);
  assert.equal(text(f.calls), "");
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


test("read-only V9 verification refreshes package and runtime evidence without publication", () => {
  const f = fixture();
  try {
    assert.notEqual(f.run({}, ["verify"]).status, 0);
    assert.equal(text(f.calls), "");
    const result = f.run({ CONFIRM: `VERIFY-BASE44-STAGED-V9:${sourceSha}`, TEST_FLAT_PULL: "yes", TEST_PREEXIST: "yes" }, ["verify"]);
    assert.equal(result.status, 0, result.stderr);
    assert.deepEqual(text(f.calls).trim().split("\n"), [
      ...aliases.map(pullCall), execCall,
    ]);
    const readiness = JSON.parse(text(f.readiness));
    assert.equal(readiness.functions.length, names.length);
    assert.equal(readiness.production_activation, false);
  } finally {
    f.cleanup();
  }
});

test("Base44 observations bind owner intake to the deployed package and run only verification", () => {
  const f = fixture();
  const output = realpathSync(mkdtempSync(join(tmpdir(), "staged-v9-observations-")));
  try {
    const result = f.run({ EXPECTED_OWNER_USER_ID: "6a498da58ef5cec1f5cd4486", BASE44_OBSERVATIONS_DIR: output, TEST_PREEXIST: "yes" }, [], collector);
    assert.equal(result.status, 0, result.stderr);
    assert.deepEqual(text(f.calls).trim().split("\n"), [
      execCall, ...aliases.map(pullCall), execCall,
    ]);
    const intake = text(join(output, "intake.json"));
    const packages = JSON.parse(text(join(output, "packages.json")));
    assert.equal(JSON.parse(intake).build_id, packages.functions[0].build_id);
    assert.doesNotMatch(intake, /unexpected_secret|do-not-copy/);
    assert.equal(JSON.parse(text(join(output, "schemas.json"))).action, "verify");
  } finally {
    f.cleanup();
    rmSync(output, { recursive: true, force: true });
  }
});

for (const mode of ["stale", "duplicate"]) test(`Base44 observations reject ${mode} intake readback`, () => {
  const f = fixture();
  const output = realpathSync(mkdtempSync(join(tmpdir(), "staged-v9-observations-")));
  try {
    const result = f.run({ EXPECTED_OWNER_USER_ID: "6a498da58ef5cec1f5cd4486", BASE44_OBSERVATIONS_DIR: output, TEST_INTAKE_MODE: mode, TEST_PREEXIST: "yes" }, [], collector);
    assert.notEqual(result.status, 0);
    assert.equal(existsSync(join(output, "intake.json")), false);
    assert.equal(existsSync(join(output, "schemas.json")), false);
  } finally {
    f.cleanup();
    rmSync(output, { recursive: true, force: true });
  }
});
