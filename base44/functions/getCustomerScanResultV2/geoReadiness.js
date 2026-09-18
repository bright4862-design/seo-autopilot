// Package-local authority boundary; mirrored in readers/writers (no cross-package imports).
export const GEO_SNAPSHOT_VERSION = "standard_review_snapshot_hmac_geo_v1";
export const GEO_VERSION = "geo_readiness_v1_experimental";
export const GEO_ADAPTER_VERSION = "geo_evidence_v1";
const CHECKS = {
 search_policy: "access", indexability: "access", discovery: "access",
 main_text: "clarity", page_identity: "clarity", template_integrity: "clarity",
 subject_identity: "entity", entity_details: "entity", schema_agreement: "entity",
 accountability: "support", date_context: "support", source_attribution: "support",
};
const LABELS = {"search_policy": "OAI-SearchBot robots directive", "indexability": "Observed search indexing directives", "discovery": "Discovery in the sampled link graph", "main_text": "Extractable text in a main content landmark", "page_identity": "Nonempty page title and primary heading", "template_integrity": "Template token syntax in ordinary text", "subject_identity": "Explicitly labelled subject name", "entity_details": "Visible semantic contact address", "schema_agreement": "Page-linked structured name agrees with primary heading", "accountability": "Article contains an identified author link", "date_context": "Article contains a labelled machine-readable date", "source_attribution": "Article quotation links its declared source"};
const ACTIONS = {"search_policy": ["Review whether the OAI-SearchBot restriction matches intended search access.", "Recheck the robots directive for the affected page after any intended change."], "indexability": ["Reconcile the observed noindex directive with sitemap inclusion or explicit search intent.", "Inspect the response and HTML directives after publication."], "template_integrity": ["Review the token syntax in ordinary page text and replace any unintended placeholder.", "Confirm the published main text no longer contains the unintended token."]};
const DIMS = ["access", "clarity", "entity", "support"];
const STATES = ["fail", "not_applicable", "not_verified", "pass"];
const BOUNDS = "unknown_outcome_range_not_statistical_confidence";
const fail = () => { throw new Error("geo_readiness_contract"); };
function check(value) { if (!value) fail(); }
function keys(value, expected) {
 check(value && typeof value === "object" && !Array.isArray(value));
 check(Object.keys(value).sort().join("|") === [...expected].sort().join("|"));
}
function same(a,b) { return JSON.stringify(sort(a)) === JSON.stringify(sort(b)); }
function sort(a) { return Array.isArray(a) ? a.map(sort) : a && typeof a === "object" ? Object.fromEntries(Object.keys(a).sort().map(k=>[k,sort(a[k])])) : a; }
const gcd = (a,b) => b ? gcd(b,a%b) : a;
function rat(n,d=1n) { n=BigInt(n); d=BigInt(d); check(d>0n); const g=gcd(n<0n?-n:n,d); return [n/g,d/g]; }
const add = (a,b) => rat(a[0]*b[1]+b[0]*a[1],a[1]*b[1]);
const div = (a,n) => rat(a[0],a[1]*BigInt(n));
const mul = (a,n) => rat(a[0]*BigInt(n),a[1]);
const ratio = (a,b) => rat(a[0]*b[1],a[1]*b[0]);
const less = (a,n,d) => a[0]*BigInt(d)<BigInt(n)*a[1];
// Match Python round(float(Fraction), 6), including binary half-even ties.
function display(a) {
 const value=Number(a[0])/Number(a[1]);
 if(value===0) return 0;
 const buffer=new ArrayBuffer(8), view=new DataView(buffer); view.setFloat64(0,value);
 const bits=view.getBigUint64(0), exponent=Number((bits>>52n)&2047n)-1023-52;
 const mantissa=(bits&((1n<<52n)-1n))+(1n<<52n);
 let n=mantissa*1000000n, d=1n;
 if(exponent>=0)n<<=BigInt(exponent); else d<<=BigInt(-exponent);
 let rounded=n/d; const remainder=n%d;
 if(2n*remainder>d || (2n*remainder===d && rounded%2n)) rounded++;
 return Number(rounded)/1e6;
}
function displayed(actual,expected) { check(typeof actual === "number" && Number.isFinite(actual) && actual===display(expected)); }
export function emptyGeoReadiness(status="not_assessed") {
 check(["not_assessed","evaluation_error"].includes(status));
 return {geo_readiness_version:GEO_VERSION,evidence_adapter_version:GEO_ADAPTER_VERSION,
 assessment_status:status,score:null,coverage:0,score_bounds:null,bounds_kind:BOUNDS,
 sample_pages:0,dimensions:{},reasons:[status],authority_verified:false,
 observations:[],findings:[],assessment_gates:{parent_authoritative:false,entry_verified:false,access_limited:false}};
}
export function validateGeoReadiness(value) {
 keys(value,Object.keys(emptyGeoReadiness()));
 const v=value;
 check(v.geo_readiness_version===GEO_VERSION && v.evidence_adapter_version===GEO_ADAPTER_VERSION && v.bounds_kind===BOUNDS && v.authority_verified===false);
 if (["not_assessed","evaluation_error"].includes(v.assessment_status)) { check(same(v,emptyGeoReadiness(v.assessment_status))); return structuredClone(v); }
 keys(v.assessment_gates,["parent_authoritative","entry_verified","access_limited"]);
 check(Object.values(v.assessment_gates).every(x=>typeof x === "boolean"));
 check(Number.isInteger(v.sample_pages) && v.sample_pages>=0 && v.sample_pages<=150);
 check(Array.isArray(v.observations) && v.observations.length===v.sample_pages*12);
 check(Array.isArray(v.findings) && v.findings.length<=3);
 const pages=new Set(), cells=new Map(); let previous="";
 for (const o of v.observations) {
  keys(o,["page_id","check_id","state","evidence_ref","reason"]);
  check(typeof o.page_id==="string" && /^p_[a-f0-9]{24}$/.test(o.page_id));
  check(Object.hasOwn(CHECKS,o.check_id) && STATES.includes(o.state));
  check(typeof o.reason==="string" && o.reason.length>0 && o.reason.length<=500);
  check(typeof o.evidence_ref==="string" && o.evidence_ref.length<=200);
  const key=o.page_id+":"+String(Object.keys(CHECKS).indexOf(o.check_id)).padStart(2,"0");
  check(key>previous); previous=key; pages.add(o.page_id); cells.set(o.page_id+":"+o.check_id,o);
  if (["pass","fail"].includes(o.state)) check(new RegExp(`^geo_evidence_v1:raw_html:${o.page_id}:${o.check_id}:[a-f0-9]{24}$`).test(o.evidence_ref));
  else check(o.evidence_ref==="");
  if (o.state==="fail") check(Object.hasOwn(ACTIONS,o.check_id));
 }
 check(pages.size===v.sample_pages);
 const masses=[], dimensions={};
 for(const dim of DIMS) {
  const checks={}, ps=[], vs=[];
  for(const [id,owner] of Object.entries(CHECKS)) {
   if(owner!==dim) continue;
   const counts=Object.fromEntries(STATES.map(s=>[s,0]));
   for(const page of pages) { const o=cells.get(page+":"+id); check(o); counts[o.state]++; }
   const applicable=v.sample_pages-counts.not_applicable;
   checks[id]={counts,applicable_or_unknown:applicable};
   if(applicable) { ps.push(rat(counts.pass,applicable)); vs.push(rat(counts.pass+counts.fail,applicable)); }
  }
  const p=ps.length?div(ps.reduce(add,rat(0)),ps.length):rat(0), c=vs.length?div(vs.reduce(add,rat(0)),vs.length):rat(0);
  masses.push([p,c]); dimensions[dim]={checks,coverage:display(c),score:c[0]?display(mul(ratio(p,c),100)):null};
 }
 const p=div(masses.map(x=>x[0]).reduce(add,rat(0)),4), c=div(masses.map(x=>x[1]).reduce(add,rat(0)),4);
 const reasons=[];
 if(!v.assessment_gates.parent_authoritative) reasons.push("parent_not_authoritative");
 if(!v.assessment_gates.entry_verified) reasons.push("entry_not_verified");
 if(less(c,4,5)) reasons.push("overall_coverage_below_80_percent");
 DIMS.forEach((d,i)=>{if(less(masses[i][1],1,2)) reasons.push(`${d}_coverage_below_50_percent`);});
 const limited=v.assessment_gates.access_limited;
 const status=limited?"access_limited":reasons.length?"insufficient_evidence":"assessed";
 check(v.assessment_status===status && same(v.reasons,limited?["access_limited"]:reasons));
 if(limited) {
  check(v.score===null && v.coverage===0 && v.score_bounds===null && same(v.dimensions,{}) && v.findings.length===0);
  check(v.observations.every(o=>o.state==="not_verified"));
 } else {
  check(same(v.dimensions,dimensions)); displayed(v.coverage,c);
  keys(v.score_bounds,["lower","upper"]);
  displayed(v.score_bounds.lower,mul(p,100)); displayed(v.score_bounds.upper,mul(add(add(p,rat(1)),rat(-c[0],c[1])),100));
  const numeric=c[0]?mul(ratio(p,c),100):rat(0);
  const score=Number((2n*numeric[0]+numeric[1])/(2n*numeric[1]));
  check(v.score===(status==="assessed"?score:null));
 }
 const failed=Object.keys(ACTIONS).sort().filter(id=>v.observations.some(o=>o.check_id===id && o.state==="fail"));
 check(v.findings.length===failed.length);
 v.findings.forEach((f,i)=>{
  keys(f,["rule_id","root_cause_id","check_id","label","affected_page_count","page_ids","evidence_samples","sample_truncated","suggested_action","verification_step"]);
  const id=failed[i], rows=v.observations.filter(o=>o.check_id===id && o.state==="fail");
  check(f.check_id===id && f.rule_id==="geo_"+id && f.root_cause_id===f.rule_id && f.label===LABELS[id]);
  check(f.suggested_action===ACTIONS[id][0] && f.verification_step===ACTIONS[id][1]);
  check(f.affected_page_count===rows.length && same(f.page_ids,rows.map(o=>o.page_id)) && f.sample_truncated===(rows.length>5));
  check(Array.isArray(f.evidence_samples) && f.evidence_samples.length===Math.min(5,rows.length));
  f.evidence_samples.forEach((s,j)=>{
   keys(s,[...Object.keys(rows[j]),"page_url"]); const {page_url,...observation}=s; check(same(observation,rows[j]));
   check(typeof page_url==="string" && page_url.length<=2048 && !/[\x00-\x1f\x7f]/.test(page_url));
   if(page_url) { let url; try { url=new URL(page_url); } catch { fail(); } check(["http:","https:"].includes(url.protocol) && url.hostname && !url.username && !url.password && !url.search && !url.hash); }
  });
 });
 return structuredClone(v);
}
export function geoReadinessSnapshotFields(row) {
 return row?.authority_seal_version===GEO_SNAPSHOT_VERSION ? {geo_readiness:validateGeoReadiness(row.geo_readiness)} : {};
}
export function geoReadinessSummary(value) {
 const v=validateGeoReadiness(value);
 return Object.fromEntries(["geo_readiness_version","evidence_adapter_version","assessment_status","score","coverage","sample_pages","score_bounds","bounds_kind"].map(k=>[k,v[k]]));
}
export function customerGeoReadiness(row,full=false) {
 const v=row?.authority_seal_version===GEO_SNAPSHOT_VERSION?validateGeoReadiness(row.geo_readiness):emptyGeoReadiness();
 return full ? {...v,authority_verified:row?.authority_seal_version===GEO_SNAPSHOT_VERSION} : geoReadinessSummary(v);
}
export function validProducerGeoReadiness(value, scan) {
 try {
  const v=validateGeoReadiness(value ?? emptyGeoReadiness());
  if (["not_assessed","evaluation_error"].includes(v.assessment_status)) return true;
  if (!v.assessment_gates.parent_authoritative || v.assessment_gates.access_limited) return false;
  const scanPages=[scan?.crawled_pages,scan?.pages,scan?.scanned_pages].find(a=>Array.isArray(a)&&a.length)||[];
  if (v.sample_pages!==scanPages.length) return false;
  if (v.assessment_gates.entry_verified) {
   const entry=scan?.submitted_url || scan?.website_url || scan?.url;
   const normalize=url=>typeof url==="string"?url.split("#")[0]:"";
   const pages=scanPages;
   if (!entry || !pages.some(p=>normalize(p.url)===normalize(entry) && p.status_code===200 && p.page_evidence_class==="usable_html" && p.geo_evidence?.accepted===true && !["fetch_error","raw_html_truncated","html_truncated","client_rendering_suspected","render_error","rendering_failed"].some(k=>p[k]) && !["challenge","block","rate_limit"].includes(p.access_block_kind))) return false;
  }
  return true;
 } catch { return false; }
}

export function validatedGeoSummary(value) {
 const expected=geoReadinessSummary(emptyGeoReadiness()); keys(value,Object.keys(expected));
 check(value.geo_readiness_version===GEO_VERSION && value.evidence_adapter_version===GEO_ADAPTER_VERSION && value.bounds_kind===BOUNDS);
 check(["assessed","insufficient_evidence","access_limited","not_assessed","evaluation_error"].includes(value.assessment_status));
 check(value.assessment_status==="assessed" ? Number.isInteger(value.score) && value.score>=0 && value.score<=100 : value.score===null);
 check(typeof value.coverage==="number" && value.coverage>=0 && value.coverage<=1);
 check(Number.isInteger(value.sample_pages) && value.sample_pages>=0 && value.sample_pages<=150);
 if(value.score_bounds!==null) { keys(value.score_bounds,["lower","upper"]); check(Object.values(value.score_bounds).every(n=>typeof n==="number" && n>=0 && n<=100) && value.score_bounds.lower<=value.score_bounds.upper); }
 return structuredClone(value);
}
