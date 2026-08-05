import { createClient } from "@base44/sdk";
import { readFileSync } from "node:fs";

const auth = JSON.parse(readFileSync("/root/.base44/auth/auth.json", "utf8"));
const base44 = createClient({ appId: "6a498732ec779dfaaeab0e53", token: auth.accessToken, requiresAuth: true });

const log = (boundary, data = {}) => console.log(JSON.stringify({ boundary, ...data }));
const unwrap = (r) => r?.data?.data || r?.data || r;

const user = await base44.auth.me();
log("user", { owner_user_id: user?.id });

const DOMAIN = "www.centerstreetlending.com";
const URL_ = "https://www.centerstreetlending.com/";

const projects = await base44.entities.BusinessProject.filter({ owner_user_id: user.id }, "-last_crawl_at", 100);
const project = (projects || []).find((p) => String(p.website_url || "").includes("centerstreetlending"));
log("project", { project_id: project?.id });
if (!project) throw new Error("no centerstreetlending project");

const requestId = `scanreq_${crypto.randomUUID()}`;
const run = await base44.entities.ScanRun.create({
  request_id: requestId, idempotency_key: requestId,
  request_fingerprint: `standard_150|${URL_}`,
  project_id: project.id, website_url: URL_, submitted_url: URL_, final_url: "",
  path_prefix: "", scan_mode: "standard_150", scan_source: "authority_boundary_probe",
  status: "queued", respect_robots_txt: true, normalized_domain: DOMAIN,
  queued_at: new Date().toISOString(), owner_user_id: user.id,
});
await base44.entities.ScanRun.update(run.id, { scan_id: run.id, status: "crawling", started_at: new Date().toISOString() });
log("scan_run_created", { scan_id: run.id });

log("scanner_function_start");
const scan = unwrap(await base44.functions.invoke("runStandard150Scan", {
  website_url: URL_, requested_start_url: URL_, crawl_path_prefix: "", strict_path_prefix: true,
  clear_previous_scan: true, business_name: project.business_name || "Center Street Lending",
  cms_platform: "custom", cms_name: "Custom / Not sure", important_keywords: [], competitor_urls: [],
  scan_mode: "standard_150", canonical_mode: "standard_150", force_internal_crawl: true,
  respect_robots_txt: true, max_competitors: 0, source: "authority_boundary_probe",
  requested_at: new Date().toISOString(), request_id: requestId, idempotency_key: requestId,
  scan_id: run.id, scan_run_id: run.id, submitted_url: URL_, normalized_domain: DOMAIN,
  require_python_scanner: true, allow_deno_fallback: false,
}));
log("scanner_function_response", {
  success: scan?.success, failure_code: scan?.failure_code || null,
  pages_crawled: scan?.pages_crawled, scanner_version: scan?.scanner_version,
  authority_attestation_status: scan?.authority_attestation_status || null,
  has_scan_attestation: Boolean(scan?.authority_scan_attestation),
  has_review_payload: Boolean(scan?.authority_review_payload),
});
if (!scan?.authority_scan_attestation || !scan?.authority_review_payload) {
  log("VERDICT", { stage: "scanner", status: scan?.authority_attestation_status || null }); process.exit(0);
}

log("review_function_start");
const ai = unwrap(await base44.functions.invoke("aiReviewScan", {
  authoritative_scan: {
    authority_review_payload: scan.authority_review_payload,
    authority_scan_attestation: scan.authority_scan_attestation,
    authority_attestation_status: scan.authority_attestation_status || "server_attested",
  },
  client_context: {
    business_name: project.business_name || "Center Street Lending",
    cms_platform: "custom", cms_name: "Custom / Not sure", important_keywords: [],
    requested_path_prefix: "", coverage_instruction: "Use the server-attested scan page counts.",
    ai_review_goal: "Create a customer-friendly FixList.",
    cms_instruction: "Tailor fixes for a custom or unknown CMS.",
    business_priority_instruction: { rule: "Prioritize by business importance.", requested_path_prefix: "" },
    output_requirements: { keep_language_simple: true, group_similar_issues: true, preserve_url_evidence_fields: true, use_scan_coverage_for_page_counts: true },
  },
}));
log("review_function_response", {
  success: ai?.success, ai_review_backend: ai?.ai_review_backend,
  python_review_fallback_used: ai?.python_review_fallback_used,
  review_version: ai?.review_version,
  archetype_classifier_version: ai?.archetype_classifier_version || ai?.site_fingerprint?.classification?.classifier_version || null,
  review_evidence_calibration_version: ai?.review_evidence_calibration_version || null,
  beta_revision_fingerprint: ai?.beta_revision_fingerprint || null,
  release_gate_eligible: ai?.release_gate_eligible,
  score_is_provisional: ai?.score_is_provisional,
  evidence_quality_blocking: ai?.evidence_quality_blocking,
  authority_attestation_status: ai?.authority_attestation_status || null,
  has_review_attestation: Boolean(ai?.authority_review_attestation),
});
if (!ai?.authority_review_attestation) {
  log("VERDICT", { stage: "review", status: ai?.authority_attestation_status || null }); process.exit(0);
}

log("persistence_start");
const p = unwrap(await base44.functions.invoke("persistScanAuthority", { scan_id: run.id, attestation: ai.authority_review_attestation }));
const proof = String(p?.scanRun?.authority_proof || "");
log("persistence_response", {
  success: p?.success, error_code: p?.error_code || null, fix_list_id: p?.fixListId || null,
  proof_is_64_lower_hex: /^[a-f0-9]{64}$/.test(proof),
  authority_seal_version: p?.scanRun?.authority_seal_version || null,
  authority_sealed_at: p?.scanRun?.authority_sealed_at || null,
  release_gate_eligible: p?.scanRun?.release_gate_eligible,
  status: p?.scanRun?.status, pages_crawled: p?.scanRun?.pages_crawled,
});
log("VERDICT", { stage: "complete", scan_id: run.id, sealed: /^[a-f0-9]{64}$/.test(proof) });
