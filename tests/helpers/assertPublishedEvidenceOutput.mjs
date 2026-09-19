import {buildRepairCards} from "../../src/lib/repairCardModel.js";
import {buildScanHandoff,serializeScanHandoff} from "../../src/lib/scanHandoff.js";
import {buildScanReportPdf} from "../../src/lib/exportScanReport.js";
import {serializeAffectedUrlsText,serializeAffectedUrlsCsv} from "../../src/lib/affectedUrlExport.js";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {webcrypto} from "node:crypto";
import {buildAuthoritySnapshot,buildPersistedAuthoritySnapshot} from "../../base44/functions/persistDurableScanAuthorityV7/authoritySnapshot.js";
import {authorityRowsFromSnapshot} from "../../base44/functions/persistDurableScanAuthorityV7/authorityRows.js";
import {authoritySnapshotFromRows,buildCustomerProjection} from "../../base44/functions/getCustomerScanResultV7/projection.js";
import {authoritySnapshotFromRows as grokSnapshot} from "../../base44/functions/grokChat/authoritySnapshot.js";
import {createAuthoritySeal,verifyAuthoritySeal} from "../../base44/functions/persistDurableScanAuthorityV7/authoritySeal.js";
const {scan,review,expectedUrls,expectedEligible=expectedUrls.length,expectedRule}=JSON.parse(readFileSync(0,"utf8"));
const snapshot=buildAuthoritySnapshot({scan,review,identity:{scan_id:"s",project_id:"p",normalized_domain:"example.com"},
  userId:"u",now:"2026-09-19T00:00:00.000Z",identityVersion:"evidence_url_identity_v2_published_route"});
const proof=await createAuthoritySeal(snapshot,"test-secret",webcrypto);
const rows=authorityRowsFromSnapshot(snapshot,{fixListId:"f",ownerUserId:"u",proof});
const data={run:{...rows.scanRun,id:"s",project_id:"p"},fixList:{...rows.fixList,id:"f"},fixItems:rows.fixItems,userId:"u"};
for(const [name,result] of [["writer",buildPersistedAuthoritySnapshot(data)],["customer",authoritySnapshotFromRows(data)],["grok",grokSnapshot({...data,scan:data.run})]]) {
  assert.deepEqual(result,snapshot,name);
  assert.equal(await verifyAuthoritySeal(result,"test-secret",proof,webcrypto),true,name);
}
const selected=buildCustomerProjection({...data,fullAccess:true,authorityVerified:true}).fixItems.filter(f=>expectedRule ? f.rule===expectedRule : f.category==="meta_description");
assert.equal(selected.length,1,expectedRule || "meta_description");
const [fix]=selected;
assert.equal(fix.page_count,expectedUrls.length);
assert.deepEqual(fix.affected_pages, expectedUrls);
assert.equal(fix.raw_finding.repair_evidence_groups[0].count,expectedUrls.length);
assert.equal(fix.priority_context.evidence_url_identity_version,"evidence_url_identity_v2_published_route");
assert.equal(fix.priority_context.affected_observed,expectedUrls.length);
assert.equal(fix.priority_context.affected_eligible,expectedEligible);
if (expectedEligible === 0) assert.equal(fix.priority_context.checked_eligible,null);

const origin = scan.website_url;
const [card] = buildRepairCards([fix]);
assert.equal(card.evidence.pageCount, expectedUrls.length);
assert.deepEqual(card.evidence.affectedPages, expectedUrls);
const handoff = JSON.parse(serializeScanHandoff(buildScanHandoff({scanRecord: {website_url: origin}, cards:[card]})));
assert.equal(handoff.fixes[0].pages_affected, expectedUrls.length);
assert.deepEqual(handoff.fixes[0].example_pages, expectedUrls.slice(0,10));
assert.equal(handoff.fixes[0].example_pages_are_partial, expectedUrls.length>10);
const pdf = buildScanReportPdf({project: {website_url:origin}, issues:[fix]}).output();
for (const url of expectedUrls) assert.ok(pdf.includes(`/URI (${url})`), url);
const item = {affectedPages:fix.affected_pages, websiteUrl:origin, original:fix, title:fix.issue_title, rule:fix.rule};
assert.equal(serializeAffectedUrlsText(item),expectedUrls.join("\n"));
const csv = serializeAffectedUrlsCsv(item);
assert.equal(csv.split("\n").length, expectedUrls.length+1);
for (const url of expectedUrls) assert.ok(csv.includes(`"${url}"`),url);
const preview=buildCustomerProjection({...data,fullAccess:false,previewAccess:true,authorityVerified:true});
assert.ok(preview.fixItems.length<=2);
for (const row of preview.fixItems) {
  for (const key of ["affected_pages","raw_finding","repair_observation_samples","priority_context","evidence_url_identity_version"])
    assert.equal(row[key],undefined,key);
}
const locked=buildCustomerProjection({...data,fullAccess:true,authorityVerified:false});
assert.deepEqual(locked.fixItems,[]);

// Render production components, with only the outbound analytics service inert.
const {renderComponent} = await import('./renderComponent.mjs');
const rowHtml = await renderComponent('src/components/fixlist/CanonicalRepairRow.jsx', {item:fix,showSuggestion:false});
assert.match(rowHtml,new RegExp(`\\b${expectedUrls.length} (?:of \\d+ (?:searchable pages|relevant pages checked)|affected pages?|pages?)\\b`));
const modalHtml = await renderComponent('src/components/issues/IssueDetailModal.jsx', {issue:{...fix,website_url:origin}});
for (const url of expectedUrls) assert.ok(modalHtml.includes(`href="${url.replaceAll('&','&amp;')}"`),url);
