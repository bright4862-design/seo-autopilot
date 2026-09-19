import assert from 'node:assert/strict';
import test from 'node:test';
import {buildRepairCards} from '../../src/lib/repairCardModel.js';
import {repairSuggestion} from '../../src/lib/repairSuggestions.js';
import {buildGeoReadinessPresentation} from '../../src/lib/geoReadinessPresentation.js';

function fix(rule){ return {rule,category:rule==='image_alt_review'?'image_alt_text':'web_dev',affected_pages:['https://example.com/a/../x'],page_count:1,evidence_url_identity_version:'evidence_url_identity_v2_published_route'}; }
test('uncertain image card and guidance ask for review before prescribing alt changes',()=>{
  const row={...fix('image_alt_review'),non_scoring:true,verification_state:'needs_verification'};
  const [card]=buildRepairCards([row]);
  assert.match(card.title,/review/i);
  assert.doesNotMatch(card.whyItMatters,/nothing to describe/i);
  const suggestion=repairSuggestion(row);
  assert.equal(suggestion.suggestionAvailable,true);
  assert.match(suggestion.suggestedFix,/purpose|decorative|review/i);
});
test('general visible-template repairs have applicable customer guidance',()=>{
  const suggestion=repairSuggestion(fix('visible_template_content'));
  assert.equal(suggestion.suggestionAvailable,true);
  assert.doesNotMatch(suggestion.suggestedFix,/location|market/i);
  assert.match(suggestion.suggestedFix,/template|source field/i);
});
test('GEO associates new template repairs only with the same published route',()=>{
  const geo={geo_readiness_version:'geo_readiness_v1_experimental',evidence_adapter_version:'geo_evidence_v1',assessment_status:'assessed',score:0,coverage:1,sample_pages:1,score_bounds:{lower:0,upper:0},bounds_kind:'unknown_outcome_range_not_statistical_confidence',authority_verified:true,
    findings:[{check_id:'template_integrity',affected_page_count:1,evidence_samples:[{page_url:'https://example.com/x'}],suggested_action:'Fix visible content'}]};
  const [card]=buildRepairCards([fix('visible_template_content')]);
  let result=buildGeoReadinessPresentation({geoReadiness:geo,cards:[card],customerAccess:'full',siteOrigin:'https://example.com'});
  assert.equal(result.actions[0].existingRepairTitle,'');
  geo.findings[0].evidence_samples[0].page_url='https://example.com/a/../x';
  result=buildGeoReadinessPresentation({geoReadiness:geo,cards:[card],customerAccess:'full',siteOrigin:'https://example.com'});
  assert.equal(result.actions[0].existingRepairTitle,card.title);
});

test('customer evidence rows show the authenticated placement and snippet', async()=>{
  const {customerRepairObservationRows}=await import('../../src/lib/repairCardModel.js');
  const row={...fix('visible_template_content'),repair_observation_count:1,repair_observation_samples:[{page_url:'https://example.com/a/../x',status:200,issue_type:'unresolved_template',excerpt:'h1: {{city}}'}]};
  const [card]=buildRepairCards([row]);
  assert.equal(customerRepairObservationRows(card,'https://example.com')[0].valueLabel,'h1: {{city}}');
});
