import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {webcrypto} from 'node:crypto';
import {buildAuthoritySnapshot,buildPersistedAuthoritySnapshot} from '../../base44/functions/persistDurableScanAuthorityV6/authoritySnapshot.js';
import {authorityRowsFromSnapshot} from '../../base44/functions/persistDurableScanAuthorityV6/authorityRows.js';
import {authoritySnapshotFromRows,buildCustomerProjection} from '../../base44/functions/getCustomerScanResultV6/projection.js';
import {authoritySnapshotFromRows as grokSnapshot} from '../../base44/functions/grokChat/authoritySnapshot.js';
import {createAuthoritySeal,verifyAuthoritySeal} from '../../base44/functions/persistDurableScanAuthorityV6/authoritySeal.js';
import {buildRepairCards,customerRepairObservationRows} from '../../src/lib/repairCardModel.js';
import {buildScanHandoff} from '../../src/lib/scanHandoff.js';
const {scan,review}=JSON.parse(readFileSync(0,'utf8'));
const snapshot=buildAuthoritySnapshot({scan,review,identity:{scan_id:'s',project_id:'p',normalized_domain:'example.com'},userId:'u',now:'2026-09-19T00:00:00.000Z',identityVersion:'evidence_url_identity_v2_published_route'});
const proof=await createAuthoritySeal(snapshot,'test-secret',webcrypto);
const rows=authorityRowsFromSnapshot(snapshot,{fixListId:'f',ownerUserId:'u',proof});
const data={run:{...rows.scanRun,id:'s',project_id:'p'},fixList:{...rows.fixList,id:'f'},fixItems:rows.fixItems,userId:'u'};
for(const result of [buildPersistedAuthoritySnapshot(data),authoritySnapshotFromRows(data),grokSnapshot({...data,scan:data.run})]) {
  assert.deepEqual(result,snapshot);
  assert.equal(await verifyAuthoritySeal(result,'test-secret',proof,webcrypto),true);
}
const customer=buildCustomerProjection({...data,fullAccess:true,authorityVerified:true});
for(const rule of ['image_alt_text','image_alt_review','visible_template_content']) {
  const fix=customer.fixItems.find(f=>f.rule===rule);
  assert.ok(fix,rule);
  const [card]=buildRepairCards([fix]);
  assert.ok(card.evidence.repairObservationSamples.length>0,rule);
  assert.ok(customerRepairObservationRows(card,scan.website_url).every(o=>o.valueLabel!=='Issue observed on this page'),rule);
  const exported=JSON.parse(JSON.stringify(buildScanHandoff({scanRecord:{website_url:scan.website_url},cards:[card]})));
  assert.deepEqual(exported.fixes[0].repair_observation_samples,card.evidence.repairObservationSamples);
  const changed=structuredClone(data);
  changed.fixItems.find(f=>f.rule===rule).raw_finding.repair_observation_samples[0].excerpt='tampered evidence';
  assert.equal(await verifyAuthoritySeal(authoritySnapshotFromRows(changed),'test-secret',proof,webcrypto),false,rule);
}
const preview=buildCustomerProjection({...data,fullAccess:false,previewAccess:true,authorityVerified:true});
assert.ok(preview.fixItems.length<=2);
assert.doesNotMatch(JSON.stringify(preview),/repair_observation_samples|decorative_state|visible_caption|unnamed_image_control/);
