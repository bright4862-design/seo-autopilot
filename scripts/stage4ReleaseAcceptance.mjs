// Stage-4 exact-source release and live customer-acceptance contract.
//
// This evaluator never deploys or mutates production. It consumes a dated
// operator record after the guarded release workflow has run and fails closed
// when exact-source, rollback, authority, reload/history, or rescan evidence is
// absent. Every live gate also carries a traceable receipt/reference; a claimed
// state with no observable receipt is not enough to establish release evidence.
import { RELEASE_FUNCTIONS } from "./base44_release_manifest.mjs";

export const STAGE4_RELEASE_RECORD_VERSION = "stage4_exact_source_customer_acceptance_v1";
export const EXPECTED_SCANNER_FUNCTIONS = Object.freeze(RELEASE_FUNCTIONS.filter((name) => name.endsWith("V6")));

function clean(value) {
  return typeof value === "string" ? value.trim() : "";
}

function time(value) {
  const parsed = Date.parse(clean(value));
  return Number.isFinite(parsed) ? parsed : null;
}

function isSha(value, width) {
  return new RegExp(`^[a-f0-9]{${width}}$`).test(clean(value));
}

function hasReceipt(value) {
  return clean(value).length >= 8;
}

function add(failures, condition, message) {
  if (!condition) failures.push(message);
}

export function evaluateStage4ReleaseAcceptance(record) {
  if (!record || typeof record !== "object" || Array.isArray(record)) {
    return { status: "not_assessed", pass: false, failures: [], blockers: ["release acceptance record missing"] };
  }
  const failures = [];
  const blockers = [];

  if (clean(record.version) !== STAGE4_RELEASE_RECORD_VERSION) blockers.push("release record version missing or unsupported");
  if (record.test_fixture === true) blockers.push("test fixture cannot establish live release acceptance");
  if (clean(record.provenance) !== "live_authorized") blockers.push("release provenance is not live_authorized");
  if (time(record.observed_at) === null) blockers.push("release observed_at missing or invalid");

  const sha = clean(record.source?.merged_sha);
  add(failures, isSha(sha, 40), "merged source SHA invalid");
  add(failures, clean(record.review?.status) === "approved", "independent review is not approved");
  add(failures, hasReceipt(record.review?.evidence_reference), "independent review evidence reference missing");
  add(failures, clean(record.ci?.conclusion) === "success", "exact-source CI is not successful");
  add(failures, clean(record.ci?.sha) === sha, "CI SHA does not match merged source SHA");
  add(failures, Number.isInteger(record.ci?.run_id) && record.ci.run_id > 0, "exact-source CI run id missing");
  add(failures, /^https:\/\/github\.com\/[^/]+\/[^/]+\/actions\/runs\/\d+$/.test(clean(record.ci?.run_url)), "exact-source CI run URL invalid");
  add(failures, record.schema?.named_schema_parity === true, "named schema parity is not verified");
  add(failures, hasReceipt(record.schema?.evidence_reference), "named schema parity evidence reference missing");

  const site = record.deployment?.site || {};
  add(failures, site.verified === true, "Base44 site is not verified");
  add(failures, clean(site.source_sha) === sha, "Base44 site source does not match merged SHA");
  add(failures, hasReceipt(site.verification_reference), "Base44 site verification receipt missing");
  const hosts = Array.isArray(site.hosts_verified) ? site.hosts_verified.map(clean) : [];
  add(failures, hosts.includes("getfixlist.com"), "getfixlist.com source identity not verified");
  add(failures, hosts.some((host) => host.endsWith(".base44.app")), "Base44-hosted source identity not verified");

  const functions = Array.isArray(record.deployment?.functions) ? record.deployment.functions : [];
  const byName = new Map(functions.map((fn) => [clean(fn?.name), fn]));
  for (const name of EXPECTED_SCANNER_FUNCTIONS) {
    const fn = byName.get(name);
    add(failures, Boolean(fn), `missing runtime identity for ${name}`);
    if (!fn) continue;
    add(failures, fn.verified === true, `${name} runtime is not verified`);
    add(failures, clean(fn.source_sha) === sha, `${name} source does not match merged SHA`);
    add(failures, Boolean(clean(fn.runtime_build_id)), `${name} runtime_build_id missing`);
    add(failures, hasReceipt(fn.verification_reference), `${name} verification receipt missing`);
  }

  const worker = record.deployment?.worker || {};
  add(failures, worker.verified === true, "worker identity is not verified");
  add(failures, clean(worker.source_sha) === sha, "worker source does not match merged SHA");
  add(failures, /^sha256:[a-f0-9]{64}$/.test(clean(worker.image_digest)), "worker image digest invalid");
  add(failures, Number(worker.traffic_percent) === 100, "worker is not at 100% traffic");
  add(failures, Boolean(clean(worker.revision)), "worker revision missing");
  add(failures, Boolean(clean(worker.rollback_target)), "rollback target missing");
  add(failures, worker.rollback_ready === true, "rollback path is not verified ready");
  add(failures, worker.private_scan_job_unauth_status === 403, "private /scan-job boundary is not verified 403");
  add(failures, hasReceipt(worker.promotion_reference), "worker promotion receipt missing");
  add(failures, hasReceipt(worker.rollback_reference), "rollback-readiness receipt missing");

  const cohort = record.acceptance?.cohort || {};
  add(failures, clean(cohort.mode) === "acceptance_only", "acceptance cohort was not acceptance_only");
  add(failures, Number.isInteger(cohort.total_claim_budget) && cohort.total_claim_budget > 0 && cohort.total_claim_budget <= 3,
    "acceptance cohort claim budget is missing or unbounded");
  add(failures, cohort.public_claims_closed === true, "public claims were not closed during bounded acceptance");
  add(failures, hasReceipt(cohort.activation_reference), "acceptance-only activation receipt missing");

  const scan = record.acceptance?.scan || {};
  const scanId = clean(scan.scan_id);
  add(failures, Boolean(scanId), "customer acceptance scan_id missing");
  add(failures, clean(scan.mode) === "standard_150", "customer acceptance did not use Standard 150");
  add(failures, clean(scan.submission_surface) === "published_customer_ui", "customer acceptance was not submitted through the published customer UI");
  add(failures, time(scan.observed_at) !== null, "customer acceptance observation timestamp missing");
  add(failures, hasReceipt(scan.evidence_reference), "customer acceptance scan evidence reference missing");
  add(failures, clean(scan.status) === "complete", "customer acceptance scan did not complete");
  add(failures, Number.isInteger(scan.pages_crawled) && scan.pages_crawled > 0 && scan.pages_crawled <= 150,
    "customer acceptance pages_crawled is outside Standard 150 bounds");
  add(failures, scan.release_gate_eligible === true, "customer acceptance is not release-gate eligible");
  add(failures, isSha(scan.authority_proof, 64), "customer acceptance authority proof invalid");
  add(failures, Boolean(clean(scan.fix_list_id)), "customer acceptance FixList id missing");
  add(failures, clean(scan.source_sha) === sha, "customer acceptance source does not match merged SHA");

  const reload = record.acceptance?.reload || {};
  add(failures, time(reload.observed_at) !== null, "reload observation timestamp missing");
  add(failures, hasReceipt(reload.evidence_reference), "reload evidence reference missing");
  add(failures, clean(reload.requested_scan_id) === scanId && clean(reload.loaded_scan_id) === scanId,
    "exact scan_id reload did not load the same scan");
  add(failures, clean(reload.fix_list_id) === clean(scan.fix_list_id), "reload returned a different FixList");
  add(failures, clean(reload.authority_proof) === clean(scan.authority_proof), "reload authority proof changed");

  const history = record.acceptance?.history || {};
  const historyIds = Array.isArray(history.scan_ids) ? history.scan_ids.map(clean) : [];
  add(failures, time(history.observed_at) !== null, "history observation timestamp missing");
  add(failures, hasReceipt(history.evidence_reference), "history evidence reference missing");
  add(failures, history.owner_scoped === true, "history is not verified owner-scoped");
  add(failures, historyIds.includes(scanId), "history does not include the exact acceptance scan_id");

  const rescan = record.acceptance?.rescan || {};
  const rescanId = clean(rescan.scan_id);
  add(failures, time(rescan.observed_at) !== null, "rescan observation timestamp missing");
  add(failures, hasReceipt(rescan.evidence_reference), "rescan evidence reference missing");
  add(failures, Boolean(rescanId) && rescanId !== scanId, "rescan scan_id missing or reused");
  add(failures, clean(rescan.parent_scan_id) === scanId, "rescan is not linked to the accepted baseline scan");
  add(failures, clean(rescan.normalized_domain) === clean(scan.normalized_domain) && Boolean(clean(scan.normalized_domain)),
    "rescan domain does not match acceptance baseline");
  add(failures, clean(rescan.status) === "complete", "rescan did not complete");
  add(failures, ["improved", "unchanged", "regressed"].includes(clean(rescan.comparison)), "rescan comparison result missing");
  add(failures, rescan.comparison_evidence_verified === true, "rescan comparison evidence is not verified");

  add(failures, record.acceptance?.closed_and_drained === true, "acceptance cohort was not closed and drained after verification");
  add(failures, hasReceipt(record.acceptance?.close_drain_reference), "acceptance close/drain receipt missing");
  add(failures, record.public_release?.opened_after_acceptance === true, "public opening was not verified to occur after acceptance");
  add(failures, record.public_release?.claims_open === true, "public claims are not verified open");
  add(failures, hasReceipt(record.public_release?.opening_reference), "public opening receipt missing");

  if (blockers.length) return { status: "not_assessed", pass: false, failures, blockers, expected_functions: EXPECTED_SCANNER_FUNCTIONS };
  if (failures.length) return { status: "failed", pass: false, failures, blockers: [], expected_functions: EXPECTED_SCANNER_FUNCTIONS };
  return { status: "pass", pass: true, failures: [], blockers: [], expected_functions: EXPECTED_SCANNER_FUNCTIONS };
}
