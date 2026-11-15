import assert from "node:assert/strict";
import {chmodSync,cpSync,existsSync,mkdtempSync,mkdirSync,readFileSync,realpathSync,rmSync,writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {spawnSync} from "node:child_process";
import test from "node:test";
import { buildManifest } from "../../scripts/base44_release_manifest.mjs";
const names=["startStandardScanJobV9","durableScanWorkerControlV9","persistDurableScanAuthorityV9","persistLimitedScanResultV9","getCustomerScanResultV9","deleteCustomerScanDataV9"];
const sourceSha="a".repeat(40);
const appId="6a498732ec779dfaaeab0e53";
const publisher="scripts/deploy-base44-staged-functions.sh";
const verifier="scripts/verify-base44-staged-functions.sh";
const collector="scripts/collect-base44-staged-observations.sh";
const text=file=>existsSync(file)?readFileSync(file,"utf8"):"";
function fixture() {
  const root=mkdtempSync(join(tmpdir(),"staged-v9-publish-"));
  const bin=join(root,"bin");mkdirSync(bin);mkdirSync(join(root,"scripts/lib"),{recursive:true});mkdirSync(join(root,"data"));mkdirSync(join(root,"base44/functions"),{recursive:true});
  for(const file of [publisher,verifier,collector,"scripts/base44_release_manifest.mjs","data/base44-function-routes.json","data/beta-crawler-revision.json"]) cpSync(file,join(root,file));
  for(const name of names) cpSync(`base44/functions/${name}`,join(root,"base44/functions",name),{recursive:true});
  const calls=join(root,"calls");const events=join(root,"events");
  writeFileSync(join(root,"scripts/lib/release-source-guard.sh"),`fixlist_require_exact_main() {\n printf 'source-guard\\n' >> "$TEST_EVENTS"\n if [[ "\${TEST_GUARD_FAIL:-}" == yes ]]; then return 2; fi\n FIXLIST_EXACT_SOURCE_SHA="$2"\n}\n`);
  writeFileSync(join(root,"scripts/lib/base44-pinned-cli.sh"),`fixlist_install_base44_cli() { FIXLIST_BASE44_CLI="$TEST_FAKE_CLI"; export FIXLIST_BASE44_CLI; }\nfixlist_require_base44_owner() {\n printf 'owner-check\\n' >> "$TEST_EVENTS"\n [[ "\${TEST_OWNER_FAIL:-}" != yes ]]\n}\n`);
  writeFileSync(join(root,"scripts/generate_release_contracts.mjs"),`import crypto from 'node:crypto';\nimport fs from 'node:fs';\nfs.appendFileSync(process.env.TEST_EVENTS,'generator:'+process.argv[2]+'\\n');\nif(process.argv[2]==='--build-id')process.stdout.write(crypto.createHash('sha256').update(process.argv[3]).digest('hex')+'\\n');\nif(process.argv[2]==='--activation-id')process.stdout.write('staged-'+process.argv[3]+'\\n');\n`);
  writeFileSync(join(root,"scripts/base44_staged_schema.mjs"),`import fs from 'node:fs';
const [operation, sourceFlag, source, reportFlag, report] = process.argv.slice(2);
if (operation !== 'verify' || sourceFlag !== '--source-sha' || source !== 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' || reportFlag !== '--report') process.exit(9);
fs.writeFileSync(report, JSON.stringify({action: operation, source_sha: source}), {flag:'wx',mode:0o600});`);
  const fakeReadback=join(bin,"readback");
  writeFileSync(fakeReadback,`#!${process.execPath}
const fs=require('node:fs');const crypto=require('node:crypto');
const name='startStandardScanJobV9';
if (!fs.readFileSync(0,'utf8').includes('staged_runtime_status')) process.exit(12);
const mode=process.env.TEST_INTAKE_MODE;
const report={schema_version:'fixlist_staged_v9_intake_readback_v1',success:true,observed_at:new Date().toISOString(),
  build_id: mode==='stale' ? 'f'.repeat(64) : crypto.createHash('sha256').update(name).digest('hex'),
  runtime_activation_id:'staged-'+name,release_fingerprint:process.env.TEST_FINGERPRINT,
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
const source = path.join(process.env.TEST_PACKAGES_ROOT, name);
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
  writeFileSync(cli,`#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' "$*" >> "$TEST_CLI_CALLS"\n[[ "$1" == --app-id && "$2" == ${appId} ]] || exit 9\nif [[ "$3" == exec && "$4" == --data-env && "$5" == prod ]]; then exec "$TEST_FAKE_READBACK"; fi\n[[ "$3" == functions ]] || exit 9\ncase "$4" in\n deploy) [[ "\${TEST_DEPLOY_FAIL:-}" != yes ]] ;;\n pull)\n  name="$5"\n  [[ "\${TEST_OMIT_PULL:-}" != "$name" ]] || exit 0\n  exec "$TEST_FAKE_PULL" "$name"\n  ;;\n *) exit 10;;\nesac\n`);chmodSync(cli,0o755);
  const curl=join(bin,"curl");
  writeFileSync(curl,`#!${process.execPath}\nconst fs=require('node:fs');const crypto=require('node:crypto');\nconst args=process.argv.slice(2);const name=args.at(-1).split('/').at(-1);\nfs.appendFileSync(process.env.TEST_EVENTS,'probe:'+name+'\\n');\nconst body={build_id:crypto.createHash('sha256').update(name).digest('hex'),runtime_activation_id:'staged-'+name,unexpected_secret:'do-not-copy'};\nif(process.env.TEST_PROBE_MODE==='stale')body.build_id='f'.repeat(64);\nif(process.env.TEST_PROBE_MODE==='activation')body.runtime_activation_id='old-activation';\nfs.writeFileSync(args[args.indexOf('-o')+1],process.env.TEST_PROBE_MODE==='malformed'?'not-json':JSON.stringify(body));\nprocess.stdout.write(process.env.TEST_PROBE_MODE==='success200'?'200':process.env.TEST_PROBE_MODE==='redirect'?'302':'405');\n`);chmodSync(curl,0o755);
  const readiness=join(tmpdir(),`${root.split('/').at(-1)}-readiness.json`);
  const run=(extra={},args=[],script=publisher)=>spawnSync("bash",[join(root,script),...args],{cwd:root,encoding:"utf8",env:{...process.env,PATH:`${bin}:${process.env.PATH}`,SOURCE_SHA:sourceSha,CONFIRM:`PUBLISH-BASE44-STAGED-V9:${sourceSha}`,BASE44_APP_ID:appId,BASE44_EXPECTED_OWNER:"owner@example.com",BASE44_API_KEY:"",READINESS_OUTPUT:readiness,PROBE_ATTEMPTS:"1",PROBE_DELAY_SECONDS:"0",TEST_CLI_CALLS:calls,TEST_EVENTS:events,TEST_FAKE_CLI:cli,TEST_FAKE_READBACK:fakeReadback,TEST_FAKE_PULL:fakePull,TEST_FINGERPRINT:JSON.parse(text(join(root,"data/beta-crawler-revision.json"))).fingerprint,TEST_PACKAGES_ROOT:join(root,"base44/functions"),...extra}});
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
    const local = buildManifest(names, "base44/functions", []);
    for (const row of readiness.functions) assert.equal(row.package_digest, local.functions[row.name].packageDigest);
    assert.match(result.stdout,/BASE44_STAGED_V9_CANDIDATE_VERIFIED/);
  }finally{f.cleanup();}
});

for(const [label,extra] of Object.entries({source_guard:{TEST_GUARD_FAIL:'yes'},owner:{TEST_OWNER_FAIL:'yes'},wrong_app:{BASE44_APP_ID:'wrong-app'},missing_sha:{SOURCE_SHA:''},confirmation:{CONFIRM:sourceSha}}))test(`V9 publication fails before deploy when ${label} is invalid`,()=>{
  const f=fixture();try{const result=f.run(extra);assert.notEqual(result.status,0);assert.equal(text(f.calls),'');assert.equal(existsSync(f.readiness),false);}finally{f.cleanup();}
});
for(const [label,extra] of Object.entries({deploy:{TEST_DEPLOY_FAIL:'yes'},missing_pull:{TEST_OMIT_PULL:names[0]},changed_pull:{TEST_TAMPER_PULL:names[0]},stale_runtime:{TEST_PROBE_MODE:'stale'},stale_activation:{TEST_PROBE_MODE:'activation'},malformed_runtime:{TEST_PROBE_MODE:'malformed'},http200:{TEST_PROBE_MODE:'success200'},redirect:{TEST_PROBE_MODE:'redirect'}}))test(`V9 ${label} failure suppresses readiness`,()=>{
  const f=fixture();try{const result=f.run(extra);assert.notEqual(result.status,0);assert.equal(existsSync(f.readiness),false);assert.doesNotMatch(result.stdout,/BASE44_STAGED_V9_CANDIDATE_VERIFIED/);}finally{f.cleanup();}
});

for (const mode of ["entry", "config", "missing", "wrapper", "extra", "symlink"]) {
  test(`V9 rejects ${mode} drift in the pinned CLI's nested pull layout`, () => {
    const f = fixture();
    try {
      const result = f.run({ TEST_TAMPER_PULL: names[0], TEST_TAMPER_MODE: mode });
      assert.notEqual(result.status, 0);
      assert.match(result.stderr, /V9 deployed package differs: startStandardScanJobV9/);
      assert.equal(existsSync(f.readiness), false);
      assert.doesNotMatch(text(f.events), /probe:/);
    } finally {
      f.cleanup();
    }
  });
}

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


test("read-only V9 verification refreshes package and runtime evidence without publication", () => {
  const f = fixture();
  try {
    assert.notEqual(f.run({}, ["verify"]).status, 0);
    assert.equal(text(f.calls), "");
    const result = f.run({ CONFIRM: `VERIFY-BASE44-STAGED-V9:${sourceSha}`, TEST_FLAT_PULL: "yes" }, ["verify"]);
    assert.equal(result.status, 0, result.stderr);
    assert.deepEqual(text(f.calls).trim().split("\n"), names.map(name => `--app-id ${appId} functions pull ${name}`));
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
    const result = f.run({ EXPECTED_OWNER_USER_ID: "6a498da58ef5cec1f5cd4486", BASE44_OBSERVATIONS_DIR: output }, [], collector);
    assert.equal(result.status, 0, result.stderr);
    assert.deepEqual(text(f.calls).trim().split("\n"), [
      `--app-id ${appId} exec --data-env prod`, ...names.map(name => `--app-id ${appId} functions pull ${name}`),
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
    const result = f.run({ EXPECTED_OWNER_USER_ID: "6a498da58ef5cec1f5cd4486", BASE44_OBSERVATIONS_DIR: output, TEST_INTAKE_MODE: mode }, [], collector);
    assert.notEqual(result.status, 0);
    assert.equal(existsSync(join(output, "intake.json")), false);
    assert.equal(existsSync(join(output, "schemas.json")), false);
  } finally {
    f.cleanup();
    rmSync(output, { recursive: true, force: true });
  }
});
