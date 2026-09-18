import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import {webcrypto} from 'node:crypto';
import {validateGeoReadiness,emptyGeoReadiness,validProducerGeoReadiness,GEO_SNAPSHOT_VERSION} from '../../base44/functions/persistDurableScanAuthorityV6/geoReadiness.js';
import {buildAuthoritySnapshot,buildPersistedAuthoritySnapshot} from '../../base44/functions/persistDurableScanAuthorityV6/authoritySnapshot.js';
import {authorityRowsFromSnapshot} from '../../base44/functions/persistDurableScanAuthorityV6/authorityRows.js';
import {authoritySnapshotFromRows,buildCustomerProjection,createAuthoritySeal,verifyAuthoritySeal} from '../../base44/functions/getCustomerScanResultV6/projection.js';
import {authoritySnapshotFromRows as grokSnapshot} from '../../base44/functions/grokChat/authoritySnapshot.js';
import * as writerPreview from '../../base44/functions/persistDurableScanAuthorityV6/customerPreviewSeal.js';
import * as readerPreview from '../../base44/functions/getCustomerScanResultV6/customerPreviewSeal.js';
const fixtures=JSON.parse(fs.readFileSync('tests/fixtures/geo/runtime.json','utf8'));
const copy=v=>structuredClone(v);
const secret='geo-test-secret';
function rows(geo=fixtures.assessed) {
 const snapshot=buildAuthoritySnapshot({scan:{...fixtures.scan,website_url:'https://example.com/',pages_found:1,pages_crawled:1},review:{geo_readiness:geo,health_score:93,recommendations:[]},identity:{scan_id:'s',project_id:'p',normalized_domain:'example.com'},userId:'u',now:'2026-09-18T12:00:00.000Z'});
 const persisted=authorityRowsFromSnapshot(snapshot,{fixListId:'f',ownerUserId:'u'});
 return {snapshot,run:{...persisted.scanRun,id:'s',project_id:'p'},fixList:{...persisted.fixList,id:'f'},fixItems:persisted.fixItems,userId:'u'};
}
test('Python producer fixtures independently validate exact arithmetic, gates and findings',()=>{
 for(const [name,v] of Object.entries(fixtures)) if(name!=='scan') assert.deepEqual(validateGeoReadiness(v),v,name);
 assert.deepEqual(validateGeoReadiness(emptyGeoReadiness()),emptyGeoReadiness());
 assert.equal(validProducerGeoReadiness(fixtures.assessed,fixtures.scan),true);
 assert.equal(validProducerGeoReadiness(fixtures.assessed,{...fixtures.scan,crawled_pages:[]}),false);
});
test('malformed worker numerics, counts, observations, findings and unbounded fields are rejected',()=>{
 const mutations=[v=>v.score=99,v=>v.coverage=.8,v=>v.score_bounds.upper=99,v=>v.dimensions.access.checks.search_policy.counts.pass=2,v=>v.observations[0].state='fail',v=>v.observations.push(v.observations[0]),v=>v.observations[0].page_id='url',v=>v.findings.push({}),v=>v.extra='secret',v=>v.assessment_gates.entry_verified=false];
 for(const mutate of mutations){const v=copy(fixtures.assessed);mutate(v);assert.throws(()=>validateGeoReadiness(v),/geo_readiness_contract/);}
 for(const mutate of [v=>v.findings[0].affected_page_count=2,v=>v.findings[0].evidence_samples[0].page_url='https://example.com/?secret=x',v=>v.findings[0].page_ids=[],v=>v.findings[0].evidence_samples[0].evidence_ref='bad']) {const v=copy(fixtures.failures);mutate(v);assert.throws(()=>validateGeoReadiness(v));}
 const bad=copy(fixtures.error);bad.score=0;assert.throws(()=>validateGeoReadiness(bad));
});
test('new snapshot survives persistence, writer readback, customer and Grok reconstruction',async()=>{
 const data=rows(fixtures.failures), {snapshot}=data;
 assert.deepEqual(authoritySnapshotFromRows(data),snapshot);
 assert.deepEqual(buildPersistedAuthoritySnapshot(data),snapshot);
 assert.deepEqual(grokSnapshot({...data,scan:data.run}),snapshot);
 const proof=await createAuthoritySeal(snapshot,secret,webcrypto);
 assert.equal(await verifyAuthoritySeal(authoritySnapshotFromRows(data),secret,proof,webcrypto),true);
 for(const key of ['score','coverage','observations']) {const altered=copy(data);if(key==='observations')altered.run.geo_readiness.observations[0].reason='tampered reason';else altered.run.geo_readiness[key]=0;try{assert.equal(await verifyAuthoritySeal(authoritySnapshotFromRows(altered),secret,proof,webcrypto),false);}catch(e){assert.match(e.message,/geo_readiness_contract/);}}
 const errored=rows(fixtures.error);assert.equal(errored.snapshot.scan.health_score,93);assert.equal(errored.snapshot.scan.geo_readiness.score,null);
});
test('paid full GEO and signed/free summary preserve entitlement without nested evidence',async()=>{
 const data=rows(fixtures.failures);data.run.authority_proof='a'.repeat(64);
 const paid=buildCustomerProjection({...data,fullAccess:true,authorityVerified:true});assert.equal(paid.run.geo_readiness.authority_verified,true);assert.equal(paid.run.geo_readiness.findings.length,2);
 const free=buildCustomerProjection({...data,previewAccess:true,fullAccess:false,authorityVerified:true});
 const payload=writerPreview.buildCustomerPreviewPayload({...data,ownerUserId:'u',fullAuthorityProof:data.run.authority_proof});
 assert.deepEqual(payload.run.geo_readiness,free.run.geo_readiness);
 const proof=await writerPreview.createCustomerPreviewProof(payload,secret,webcrypto);
 assert.equal(await readerPreview.verifyCustomerPreviewProof(payload,secret,proof,webcrypto),true);
 const signed=buildCustomerProjection({run:payload.run,fixList:payload.fixList,fixItems:payload.fixItems,previewAccess:true,fullAccess:false,authorityVerified:true,signedPreview:true});
 assert.deepEqual(signed.run.geo_readiness,free.run.geo_readiness);
 for(const key of ['findings','observations','dimensions','assessment_gates']) assert.equal(key in signed.run.geo_readiness,false);
 assert.equal(JSON.stringify(signed.run.geo_readiness).includes('https:'),false);
 const tampered=copy(payload);tampered.run.geo_readiness.coverage=0;assert.equal(await readerPreview.verifyCustomerPreviewProof(tampered,secret,proof,webcrypto),false);
 assert.equal('geo_readiness' in buildCustomerProjection({...data,fullAccess:false,authorityVerified:false}).run,false);
});
test('package-local GEO validators remain identical',()=>{
 const expected=fs.readFileSync('base44/functions/persistDurableScanAuthorityV6/geoReadiness.js','utf8');
 for(const prefix of ['persistDurableScanAuthority','getCustomerScanResult'])for(const suffix of ['', 'V2','V3','V4','V5','V6'])assert.equal(fs.readFileSync(`base44/functions/${prefix}${suffix}/geoReadiness.js`,'utf8'),expected);
 assert.equal(fs.readFileSync('base44/functions/grokChat/geoReadiness.js','utf8'),expected);
});
test('frozen pre-GEO v1-v6 HMAC bytes survive injection and detect historical row tampering',async()=>{
 const historical=JSON.parse(fs.readFileSync('tests/fixtures/geo/historical-seals.json','utf8'));
 for(const {data,snapshot,proof} of historical){
  assert.deepEqual(authoritySnapshotFromRows(data),snapshot);
  assert.equal(await verifyAuthoritySeal(authoritySnapshotFromRows(data),secret,proof,webcrypto),true);
  data.run.geo_readiness=fixtures.assessed;
  assert.deepEqual(authoritySnapshotFromRows(data),snapshot);
  assert.equal(buildCustomerProjection({...data,fullAccess:true,authorityVerified:true}).run.geo_readiness.assessment_status,'not_assessed');
  data.run.health_score=0;
  assert.equal(await verifyAuthoritySeal(authoritySnapshotFromRows(data),secret,proof,webcrypto),false);
 }
});
test('historical v1 preview proof uses its exact domain and payload, with no GEO backfill',async()=>{
 const data=rows();data.run.authority_seal_version='standard_review_snapshot_hmac_v6_report_evidence';
 const payload=writerPreview.buildCustomerPreviewPayload({...data,ownerUserId:'u',fullAuthorityProof:'a'.repeat(64)});
 assert.equal('geo_readiness' in payload.run,false);
 const legacyEnvelope={domain:'fixlist_customer_preview_v1',version:'standard_customer_preview_hmac_v1',payload};
 const proof=await createAuthoritySeal(legacyEnvelope,secret,webcrypto);
 assert.equal(await readerPreview.verifyCustomerPreviewProof(payload,secret,proof,webcrypto),true);
 assert.equal(readerPreview.hasCustomerPreviewArtifact({...data.run,customer_preview_seal_version:'standard_customer_preview_hmac_v1',customer_preview_payload:JSON.stringify(payload),customer_preview_proof:proof,customer_preview_sealed_at:data.run.authority_sealed_at}),true);
});
test('128-page six-decimal binary tie matches Python half-even without weakening exact gates',()=>{
 const oracle=JSON.parse(fs.readFileSync('tests/fixtures/geo/rounding-oracle.json','utf8'));
 const observations=[];
 for(let i=0;i<128;i++)for(const o of fixtures.assessed.observations){const page_id='p_'+i.toString(16).padStart(24,'0');observations.push({page_id,check_id:o.check_id,state:i===0?'pass':'not_verified',evidence_ref:i===0?`geo_evidence_v1:raw_html:${page_id}:${o.check_id}:${'a'.repeat(24)}`:'',reason:'fixture'});}
 const v={...oracle,evidence_adapter_version:'geo_evidence_v1',observations,findings:[],assessment_gates:{parent_authoritative:true,entry_verified:true,access_limited:false}};
 assert.equal(v.coverage,.007812);assert.deepEqual(validateGeoReadiness(v),v);
});
test('entry verification never substitutes an alternate trailing-slash resource',()=>{
 const scan=copy(fixtures.scan);scan.submitted_url='https://example.com';
 assert.equal(validProducerGeoReadiness(fixtures.assessed,scan),false);
 scan.submitted_url='https://example.com/#section';
 assert.equal(validProducerGeoReadiness(fixtures.assessed,scan),true);
});
test('missing persisted GEO and producer sample omission fail closed',()=>{
 const data=rows(emptyGeoReadiness());delete data.run.geo_readiness;
 assert.throws(()=>authoritySnapshotFromRows(data),/geo_readiness_contract/);
 assert.throws(()=>buildPersistedAuthoritySnapshot(data),/geo_readiness_contract/);
 const scan=copy(fixtures.scan);scan.crawled_pages.push({...scan.crawled_pages[0],url:'https://example.com/other'});
 assert.equal(validProducerGeoReadiness(fixtures.assessed,scan),false);
});
test('schema keeps GEO server-owned and every customer reader accepts the internal GEO version',()=>{
 const schema=JSON.parse(fs.readFileSync('base44/entities/ScanRun.jsonc','utf8'));
 assert.equal(schema.properties.geo_readiness.type,'object');assert.equal(schema.properties.geo_readiness.rls.write.user_condition.role,'admin');assert.equal(schema.rls.read.user_condition.role,'admin');
 for(const suffix of ['', 'V2','V3','V4','V5','V6']) {
  const entry=fs.readFileSync(`base44/functions/getCustomerScanResult${suffix}/entry.ts`,'utf8');
  assert.match(entry,/const ACCEPTED_AUTHORITY_VERSIONS = new Set\(\[[\s\S]*?"standard_review_snapshot_hmac_geo_v1"/);
  const compatibility=fs.readFileSync(`base44/functions/getCustomerScanResult${suffix}/releaseCompatibility.js`,'utf8');assert.match(compatibility,/9e4901da590017e1/);
 }
});
