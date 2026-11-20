// Stage-4 exact-source release and live customer-acceptance contract.
//
// This evaluator never deploys or mutates production. It consumes a dated
// operator record after the guarded release workflow has run and fails closed
// when exact-source, rollback, authority, reload/history, or rescan evidence is
// absent. Every live gate also carries a traceable receipt/reference; a claimed
// state with no observable receipt is not enough to establish release evidence.
import { readFileSync } from "node:fs";
import { RELEASE_FUNCTIONS } from "./base44_release_manifest.mjs";
import { RELEASE_FINGERPRINT, RELEASE_COMPONENT_VERSIONS } from "../src/lib/generatedReleaseContract.js";

export const STAGE4_RELEASE_RECORD_VERSION = "stage4_exact_source_customer_acceptance_v1";
export const SCANNER_RUNTIME_ROLES = Object.freeze([
  "startStandardScanJob",
  "durableScanWorkerControl",
  "persistDurableScanAuthority",
  "persistLimitedScanResult",
  "getCustomerScanResult",
  "deleteCustomerScanData",
]);

function scannerRuntimeContract(functionNames) {
  const matches = [];
  for (const role of SCANNER_RUNTIME_ROLES) {
    const candidates = functionNames.filter((name) => new RegExp(`^${role}V\\d+$`).test(name));
    if (candidates.length === 1) matches.push(candidates[0]);
  }
  const generations = new Set(matches.map((name) => name.match(/(V\d+)$/)?.[1]).filter(Boolean));
  return {
    functions: matches,
    route_generation: matches.length === SCANNER_RUNTIME_ROLES.length && generations.size === 1
      ? [...generations][0]
      : null,
  };
}

const SOURCE_RUNTIME_CONTRACT = scannerRuntimeContract(RELEASE_FUNCTIONS);
export const EXPECTED_SCANNER_FUNCTIONS = Object.freeze(SOURCE_RUNTIME_CONTRACT.functions);
export const EXPECTED_SCANNER_ROUTE_GENERATION = SOURCE_RUNTIME_CONTRACT.route_generation;

// Each routed Base44 package already carries a source-generated SHA-256 build ID.
// A nonempty runtime label is not evidence that the deployed package matches.
function sourcePackageBuildId(name) {
  if (!/^[A-Za-z][A-Za-z0-9]*$/.test(name)) return "";
  try {
    const source = readFileSync(new URL(`../base44/functions/${name}/generatedBuildId.js`, import.meta.url), "utf8");
    return source.match(/^export const FUNCTION_BUILD_ID = "([0-9a-f]{64})";$/m)?.[1] || "";
  } catch {
    return "";
  }
}

export const EXPECTED_SCANNER_BUILD_IDS = Object.freeze(Object.fromEntries(
  EXPECTED_SCANNER_FUNCTIONS.map((name) => [name, sourcePackageBuildId(name)]),
));

// The disabled-first checkout stop is packaged separately from the six scanner
// routes; a green scanner roster cannot prove its deployed package identity.
const EXPECTED_CHECKOUT_BUILD_ID = sourcePackageBuildId("createAccessCheckout");

function clean(value) {
  return typeof value === "string" ? value.trim() : "";
}

function time(value) {
  const parsed = Date.parse(clean(value));
  return Number.isFinite(parsed) ? parsed : null;
}

// Internal chronology only: timestamps are not themselves authenticated receipts.
function observedAfter(later, earlier, strict = false) {
  const late = time(later);
  const early = time(earlier);
  return late !== null && early !== null && (strict ? late > early : late >= early);
}

function isSha(value, width) {
  return new RegExp(`^[a-f0-9]{${width}}$`).test(clean(value));
}

function hasReceipt(value) {
  return clean(value).length >= 8;
}

// Exact generated release map, not a subset or a source-SHA-only assertion.
function matchesSourceComponentVersions(candidate) {
  if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) return false;
  const expected = Object.keys(RELEASE_COMPONENT_VERSIONS);
  return Object.keys(candidate).length === expected.length
    && expected.every((key) => Object.hasOwn(candidate, key)
      && candidate[key] === RELEASE_COMPONENT_VERSIONS[key]);
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

  add(failures, EXPECTED_SCANNER_FUNCTIONS.length === SCANNER_RUNTIME_ROLES.length && Boolean(EXPECTED_SCANNER_ROUTE_GENERATION),
    "source release manifest does not declare one complete scanner runtime generation");
  add(failures, clean(record.deployment?.route_generation) === EXPECTED_SCANNER_ROUTE_GENERATION,
    "deployed scanner route generation does not match source release manifest");

  const sha = clean(record.source?.merged_sha);
  add(failures, isSha(sha, 40), "merged source SHA invalid");
  add(failures, clean(record.review?.status) === "approved", "independent review is not approved");
  add(failures, hasReceipt(record.review?.evidence_reference), "independent review evidence reference missing");
  add(failures, clean(record.ci?.conclusion) === "success", "exact-source CI is not successful");
  add(failures, clean(record.ci?.sha) === sha, "CI SHA does not match merged source SHA");
  const ciRunId = record.ci?.run_id;
  const validCiRunId = Number.isSafeInteger(ciRunId) && ciRunId > 0;
  add(failures, validCiRunId, "exact-source CI run id missing or unsafe");
  add(failures,
    validCiRunId && clean(record.ci?.run_url)
      === `https://github.com/bright4862-design/seo-autopilot/actions/runs/${ciRunId}`,
    "exact-source CI run URL invalid or not bound to run id/repository");
  add(failures, record.schema?.named_schema_parity === true, "named schema parity is not verified");
  add(failures, hasReceipt(record.schema?.evidence_reference), "named schema parity evidence reference missing");

  const site = record.deployment?.site || {};
  add(failures, site.verified === true, "Base44 site is not verified");
  add(failures, clean(site.source_sha) === sha, "Base44 site source does not match merged SHA");
  add(failures, hasReceipt(site.verification_reference), "Base44 site verification receipt missing");
  const hosts = Array.isArray(site.hosts_verified) ? site.hosts_verified.map(clean) : [];
  add(failures, hosts.includes("getfixlist.com"), "getfixlist.com source identity not verified");
  add(failures, hosts.includes("getfixlist.base44.app"), "Base44-hosted source identity not verified");

  // Independently attest the live checkout package, even while checkout is
  // disabled. No value here activates checkout or authorizes payments.
  const checkout = record.deployment?.checkout || {};
  add(failures, clean(checkout.name) === "createAccessCheckout",
    "checkout runtime function identity is not verified");
  add(failures, checkout.verified === true, "checkout runtime is not verified");
  add(failures, clean(checkout.source_sha) === sha, "checkout source does not match merged SHA");
  add(failures, /^[a-f0-9]{64}$/.test(EXPECTED_CHECKOUT_BUILD_ID || ""),
    "source checkout package build ID missing or invalid");
  add(failures, clean(checkout.runtime_build_id) === EXPECTED_CHECKOUT_BUILD_ID,
    "checkout runtime package build ID does not match frozen source");
  add(failures, hasReceipt(checkout.verification_reference),
    "checkout runtime verification receipt missing");

  const functions = Array.isArray(record.deployment?.functions) ? record.deployment.functions : [];
  const functionNames = functions.map((fn) => clean(fn?.name));
  const expectedNames = new Set(EXPECTED_SCANNER_FUNCTIONS);
  // A Map silently overwrites duplicate names. A valid final row must not conceal
  // a conflicting runtime observation, nor may an extra V8/V9 route be ignored.
  add(failures, functions.length === EXPECTED_SCANNER_FUNCTIONS.length
    && new Set(functionNames).size === functions.length
    && functionNames.every((name) => expectedNames.has(name)),
  "Base44 runtime identity roster must contain exactly the distinct source-declared functions");
  const byName = new Map(functions.map((fn) => [clean(fn?.name), fn]));
  for (const name of EXPECTED_SCANNER_FUNCTIONS) {
    const fn = byName.get(name);
    add(failures, Boolean(fn), `missing runtime identity for ${name}`);
    if (!fn) continue;
    add(failures, fn.verified === true, `${name} runtime is not verified`);
    add(failures, clean(fn.source_sha) === sha, `${name} source does not match merged SHA`);
    add(failures, Boolean(clean(fn.runtime_build_id)), `${name} runtime_build_id missing`);
    const expectedBuildId = EXPECTED_SCANNER_BUILD_IDS[name];
    add(failures, /^[a-f0-9]{64}$/.test(expectedBuildId || ""), `${name} source package build ID missing or invalid`);
    add(failures, clean(fn.runtime_build_id) === expectedBuildId,
      `${name} runtime package build ID does not match frozen source`);
    add(failures, hasReceipt(fn.verification_reference), `${name} verification receipt missing`);
  }

  const worker = record.deployment?.worker || {};
  add(failures, worker.verified === true, "worker identity is not verified");
  add(failures, clean(worker.source_sha) === sha, "worker source does not match merged SHA");
  add(failures, clean(worker.beta_revision_fingerprint) === RELEASE_FINGERPRINT,
    "worker release fingerprint does not match frozen source");
  add(failures, matchesSourceComponentVersions(worker.component_versions),
    "worker component versions do not match frozen source");
  add(failures, /^sha256:[a-f0-9]{64}$/.test(clean(worker.image_digest)), "worker image digest invalid");
  add(failures, Number(worker.traffic_percent) === 100, "worker is not at 100% traffic");
  add(failures, Boolean(clean(worker.revision)), "worker revision missing");
  add(failures, Boolean(clean(worker.rollback_target)), "rollback target missing");
  // A rollback to the same 100%-serving revision is not an available recovery path.
  add(failures, !clean(worker.revision) || !clean(worker.rollback_target)
    || clean(worker.rollback_target) !== clean(worker.revision),
    "rollback target must differ from serving worker revision");
  add(failures, worker.rollback_ready === true, "rollback path is not verified ready");
  add(failures, worker.private_scan_job_unauth_status === 403, "private /scan-job boundary is not verified 403");
  add(failures, hasReceipt(worker.promotion_reference), "worker promotion receipt missing");
  add(failures, hasReceipt(worker.rollback_reference), "rollback-readiness receipt missing");

  const cohort = record.acceptance?.cohort || {};
  add(failures, clean(cohort.mode) === "acceptance_only", "acceptance cohort was not acceptance_only");
  // Baseline scan and its linked rescan each require a fresh owner claim.
  // Completing a scan does not refund its admission quota.
  add(failures, Number.isInteger(cohort.total_claim_budget) && cohort.total_claim_budget >= 2 && cohort.total_claim_budget <= 3,
    "acceptance cohort total claim budget cannot cover baseline and rescan");
  add(failures, Number.isInteger(cohort.per_owner_claim_budget) && cohort.per_owner_claim_budget >= 2
    && cohort.per_owner_claim_budget <= cohort.total_claim_budget,
    "acceptance cohort per-owner claim budget cannot cover baseline and rescan");
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
  add(failures, clean(scan.beta_revision_fingerprint) === RELEASE_FINGERPRINT,
    "customer acceptance fingerprint does not match frozen source");

  const reload = record.acceptance?.reload || {};
  // The service-role ScanRun holds the authority HMAC; the independently
  // verifying customer reader deliberately never exposes its proof bytes.
  // Consume an identity-only extract of the sanitized V9 response instead
  // of copying the stored HMAC into a fictional customer-reload field.
  const customer = reload.customer_result || {};
  add(failures, time(reload.observed_at) !== null, "reload observation timestamp missing");
  add(failures, observedAfter(reload.observed_at, scan.observed_at),
    "reload observation precedes accepted scan");
  add(failures, hasReceipt(reload.evidence_reference), "reload evidence reference missing");
  add(failures, customer.success === true, "customer reload response not successful");
  add(failures, clean(reload.requested_scan_id) === scanId
    && clean(customer.scan_id) === scanId && clean(customer.run?.id) === scanId,
    "exact scan_id reload did not load the same scan");
  add(failures, clean(customer.fix_list_id) === clean(scan.fix_list_id)
    && clean(customer.fixList?.id) === clean(scan.fix_list_id)
    && clean(customer.fixList?.scan_run_id) === scanId,
    "reload returned a different FixList");
  add(failures, Boolean(clean(scan.project_id))
    && clean(customer.run?.project_id) === clean(scan.project_id)
    && clean(customer.fixList?.project_id) === clean(scan.project_id),
    "customer reload project does not match persisted ScanRun");
  add(failures, clean(customer.run?.status) === "complete"
    && clean(customer.run?.beta_revision_fingerprint) === RELEASE_FINGERPRINT,
    "customer reload is not the completed current-release result");
  // Proof bytes must stay in private persistence evidence, not in a reported
  // owner-facing response; no copied proof may count as reader verification.
  add(failures, !Object.hasOwn(reload, "authority_proof")
    && !Object.hasOwn(customer, "authority_proof")
    && !Object.hasOwn(customer.run || {}, "authority_proof")
    && !Object.hasOwn(customer.fixList || {}, "authority_proof"),
    "customer reload must not echo private persisted proof");
  add(failures, clean(customer.access) === "full",
    "customer reload did not return full-access FixList");
  add(failures, customer.authority_verified === true,
    "customer reload did not verify full signed authority");
  add(failures, customer.release_contract_current === true,
    "customer reload did not verify current release contract");

  const history = record.acceptance?.history || {};
  const historyIds = Array.isArray(history.scan_ids) ? history.scan_ids.map(clean) : [];
  add(failures, time(history.observed_at) !== null, "history observation timestamp missing");
  add(failures, observedAfter(history.observed_at, scan.observed_at),
    "history observation precedes accepted scan");
  add(failures, hasReceipt(history.evidence_reference), "history evidence reference missing");
  add(failures, history.owner_scoped === true, "history is not verified owner-scoped");
  add(failures, historyIds.includes(scanId), "history does not include the exact acceptance scan_id");

  const rescan = record.acceptance?.rescan || {};
  const rescanId = clean(rescan.scan_id);
  add(failures, time(rescan.observed_at) !== null, "rescan observation timestamp missing");
  add(failures, observedAfter(rescan.observed_at, scan.observed_at, true),
    "rescan observation must follow accepted scan");
  add(failures, hasReceipt(rescan.evidence_reference), "rescan evidence reference missing");
  add(failures, Boolean(rescanId) && rescanId !== scanId, "rescan scan_id missing or reused");
  add(failures, clean(rescan.parent_scan_id) === scanId, "rescan is not linked to the accepted baseline scan");
  // A matching parent ID and domain are insufficient if the saved rescan
  // belongs to a different owner/project. Fail closed on missing identity.
  add(failures, Boolean(clean(scan.project_id)) && clean(rescan.project_id) === clean(scan.project_id),
    "rescan project does not match acceptance baseline");
  add(failures, clean(rescan.normalized_domain) === clean(scan.normalized_domain) && Boolean(clean(scan.normalized_domain)),
    "rescan domain does not match acceptance baseline");
  add(failures, clean(rescan.status) === "complete", "rescan did not complete");
  add(failures, clean(rescan.mode) === "standard_150", "rescan was not Standard 150");
  add(failures, Number.isInteger(rescan.pages_crawled) && rescan.pages_crawled > 0 && rescan.pages_crawled <= 150,
    "rescan pages_crawled is outside Standard 150 bounds");
  add(failures, isSha(rescan.authority_proof, 64), "rescan authority proof missing or invalid");
  add(failures, clean(rescan.authority_proof) !== clean(scan.authority_proof), "rescan reused baseline authority proof");
  add(failures, Boolean(clean(rescan.fix_list_id)), "rescan FixList id missing");
  // Persistence owns FixLists by exact ScanRun. Reusing the baseline FixList
  // for a nominally distinct rescan is not a second saved customer result.
  // A missing ID is already rejected above; emit the distinctness failure
  // only for a supplied ID, preserving one diagnostic per missing field.
  if (clean(rescan.fix_list_id)) {
    add(failures, clean(rescan.fix_list_id) !== clean(scan.fix_list_id),
      "rescan FixList must differ from baseline acceptance FixList");
  }
  add(failures, clean(rescan.source_sha) === sha, "rescan source does not match merged SHA");
  // An independently saved comparison scan must also use the accepted worker
  // release and carry authority eligibility; a shaped HMAC is not sufficient.
  add(failures, clean(rescan.beta_revision_fingerprint) === RELEASE_FINGERPRINT,
    "rescan fingerprint does not match frozen source");
  add(failures, rescan.release_gate_eligible === true,
    "rescan is not release-gate eligible");
  add(failures, ["improved", "unchanged", "regressed"].includes(clean(rescan.comparison)), "rescan comparison result missing");
  add(failures, rescan.comparison_evidence_verified === true, "rescan comparison evidence is not verified");

  // A persisted rescan is not a verified *customer* rescan until the published
  // reader reopens its own signed result. The sanitized response must bind to
  // the distinct ScanRun/FixList, owner project and frozen release. A copied
  // HMAC or the original scan's verified reload cannot establish this.
  const rescanReload = record.acceptance?.rescan_reload || {};
  const rescanCustomer = rescanReload.customer_result || {};
  add(failures, time(rescanReload.observed_at) !== null,
    "rescan customer reload observation timestamp missing");
  add(failures, observedAfter(rescanReload.observed_at, rescan.observed_at, true),
    "rescan customer reload must follow completed rescan");
  add(failures, hasReceipt(rescanReload.evidence_reference),
    "rescan customer reload evidence reference missing");
  add(failures, rescanCustomer.success === true,
    "rescan customer reload response not successful");
  add(failures, clean(rescanReload.requested_scan_id) === rescanId
    && clean(rescanCustomer.scan_id) === rescanId
    && clean(rescanCustomer.run?.id) === rescanId,
    "rescan customer reload did not return exact ScanRun");
  add(failures, clean(rescanCustomer.fix_list_id) === clean(rescan.fix_list_id)
    && clean(rescanCustomer.fixList?.id) === clean(rescan.fix_list_id)
    && clean(rescanCustomer.fixList?.scan_run_id) === rescanId,
    "rescan customer reload returned a different FixList");
  add(failures, Boolean(clean(rescan.project_id))
    && clean(rescanCustomer.run?.project_id) === clean(rescan.project_id)
    && clean(rescanCustomer.fixList?.project_id) === clean(rescan.project_id),
    "rescan customer reload project does not match persisted rescan");
  add(failures, clean(rescanCustomer.run?.status) === "complete"
    && clean(rescanCustomer.run?.beta_revision_fingerprint) === RELEASE_FINGERPRINT,
    "rescan customer reload is not the completed current-release result");
  add(failures, !Object.hasOwn(rescanReload, "authority_proof")
    && !Object.hasOwn(rescanCustomer, "authority_proof")
    && !Object.hasOwn(rescanCustomer.run || {}, "authority_proof")
    && !Object.hasOwn(rescanCustomer.fixList || {}, "authority_proof"),
    "rescan customer reload must not echo private persisted proof");
  add(failures, clean(rescanCustomer.access) === "full",
    "rescan customer reload did not return full-access FixList");
  add(failures, rescanCustomer.authority_verified === true,
    "rescan customer reload did not verify full signed authority");
  add(failures, rescanCustomer.release_contract_current === true,
    "rescan customer reload did not verify current release contract");

  add(failures, record.acceptance?.closed_and_drained === true, "acceptance cohort was not closed and drained after verification");
  add(failures, hasReceipt(record.acceptance?.close_drain_reference), "acceptance close/drain receipt missing");
  add(failures, record.public_release?.opened_after_acceptance === true, "public opening was not verified to occur after acceptance");
  add(failures, record.public_release?.claims_open === true, "public claims are not verified open");
  add(failures, hasReceipt(record.public_release?.opening_reference), "public opening receipt missing");

  if (blockers.length) return { status: "not_assessed", pass: false, failures, blockers, expected_functions: EXPECTED_SCANNER_FUNCTIONS };
  if (failures.length) return { status: "failed", pass: false, failures, blockers: [], expected_functions: EXPECTED_SCANNER_FUNCTIONS };
  return { status: "pass", pass: true, failures: [], blockers: [], expected_functions: EXPECTED_SCANNER_FUNCTIONS };
}
