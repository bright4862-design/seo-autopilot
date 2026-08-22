import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path) => readFileSync(path, "utf8");
const bootstrap = read("scripts/bootstrap-fixlist-admission-coordinator.sh");
const deployCoordinator = read("scripts/deploy_admission_coordinator.sh");
const configureBase44 = read("scripts/configure-base44-beta-admission.sh");
const deployFunctions = read("scripts/deploy-base44-beta-functions.sh");
const deploySite = read("scripts/deploy-base44-beta-site.sh");
const verifySite = read("scripts/verify-base44-site.sh");
const mainEntry = read("src/main.jsx");
const workerCandidate = read("scripts/build-worker-candidate.sh");
const workerBuild = read("cloudbuild.durable-worker.yaml");
const workerMain = read("scanner-api/app/main.py");
const coordinatorMain = read("admission-coordinator/main.py");
const gatewayDeploy = read("scripts/deploy_dispatch_gateway.sh");
const gatewayBootstrap = read("scripts/bootstrap-fixlist-dispatch-gateway.sh");
const workflow = read(".github/workflows/fixlist-cloud-operator.yml");
const cloudOperator = read("scripts/fixlist-cloud-operator.sh");
const intakeControl = read("scripts/set-base44-scan-intake.sh");
const connectivityControl = read("scripts/set-base44-admission-connectivity.sh");
const intakeWorkflow = read(".github/workflows/fixlist-base44-scan-intake.yml");
const connectivityWorkflow = read(".github/workflows/fixlist-base44-admission-connectivity.yml");
const cliHelper = read("scripts/lib/base44-pinned-cli.sh");
const sourceGuard = read("scripts/lib/release-source-guard.sh");

const releaseMutationScripts = [
  bootstrap,
  deployCoordinator,
  configureBase44,
  deployFunctions,
  workerCandidate,
];

test("one-time admission bootstrap is owner-confirmed and creates only dedicated control-plane resources", () => {
  assert.match(bootstrap, /BOOTSTRAP-ADMISSION-INFRA/);
  assert.match(bootstrap, /fixlist-scan-admission-coordinator/);
  assert.match(bootstrap, /fixlist-admission-coordinator@/);
  assert.match(bootstrap, /FIRESTORE_DATABASE:-fixlist-admission/);
  assert.match(bootstrap, /firestore databases create[\s\S]*--type=firestore-native[\s\S]*--delete-protection/);
  assert.match(bootstrap, /roles\/datastore\.user/);
  assert.match(bootstrap, /roles\/secretmanager\.secretAccessor/);
  assert.match(bootstrap, /roles\/iam\.serviceAccountUser/);
  assert.match(bootstrap, /roles\/run\.developer/);
  assert.match(bootstrap, /SET-DRAIN-QUEUE-SAFE-BETA/);
  assert.match(bootstrap, /roles\/cloudtasks\.enqueuer/);
  assert.doesNotMatch(bootstrap, /--role=["\']?roles\/run\.admin/);
  assert.doesNotMatch(bootstrap, /service-accounts keys create|iam service-accounts keys create/);
});

test("coordinator source deployment pins exact main, build identity, database, source SHA and signing-secret reference", () => {
  assert.match(deployCoordinator, /fixlist_require_exact_main/);
  assert.match(deployCoordinator, /--build-service-account="\$BUILD_SA_RESOURCE"/);
  assert.match(deployCoordinator, /--service-account="\$RUNTIME_SA"/);
  assert.match(deployCoordinator, /FIRESTORE_DATABASE=\$DATABASE/);
  assert.match(deployCoordinator, /FIXLIST_COORDINATOR_SOURCE_SHA=\$SOURCE_SHA/);
  assert.match(deployCoordinator, /SCAN_EVIDENCE_SIGNING_KEY=\$\{SIGNING_SECRET\}:\$\{SIGNING_VERSION\}/);
  assert.match(deployCoordinator, /unsigned coordinator mutation returned/);
  assert.match(coordinatorMain, /FIXLIST_COORDINATOR_SOURCE_SHA/);
  assert.match(coordinatorMain, /"source_sha": SOURCE_SHA/);
});

test("coordinator redeploy reuses the deployed numeric operator-secret reference before enumeration", () => {
  const serviceLookup = deployCoordinator.indexOf('gcloud run services describe "$SERVICE"');
  const operatorRef = deployCoordinator.indexOf("ADMISSION_OPERATOR_SIGNING_KEY");
  const versionList = deployCoordinator.indexOf('gcloud secrets versions list "$OPERATOR_SECRET"');
  assert.ok(serviceLookup >= 0, "existing coordinator lookup is missing");
  assert.ok(operatorRef > serviceLookup, "operator secret reference is not read from the deployed coordinator");
  assert.ok(versionList > operatorRef, "secret enumeration must remain a fallback only");
  assert.match(deployCoordinator, /name == expected_name and version\.isdigit\(\)/);
  assert.doesNotMatch(deployCoordinator, /secrets versions access/);
});

test("Base44 admission configuration is disabled-first, entitlement-owned and additive", () => {
  assert.match(configureBase44, /BETA_SCAN_ADMISSION_ENABLED=false/);
  assert.match(configureBase44, /BETA_CHECKOUT_ENABLED=false/);
  assert.match(configureBase44, /SCAN_ADMISSION_COORDINATOR_URL=\$COORD_URL/);
  assert.match(configureBase44, /SCAN_DRAIN_QUEUE_PATH=\$DRAIN_QUEUE_PATH/);
  assert.doesNotMatch(configureBase44, /BETA_COHORT_ALLOWED_USER_IDS=/);
  assert.doesNotMatch(configureBase44, /len\(ids\)/);
  assert.match(configureBase44, /v\.get\('source_sha'\)==expected/);
  assert.doesNotMatch(configureBase44, /BETA_SCAN_ADMISSION_ENABLED=true|BETA_CHECKOUT_ENABLED=true/);
  assert.doesNotMatch(configureBase44, /SCAN_EVIDENCE_SIGNING_KEY=/);
});

test("Base44 release deploy names the explicit durable functions and never reconciles entities or the site", () => {
  const expected = [
    "startStandardScanJob",
    "durableScanWorkerControl",
    "persistDurableScanAuthority",
    "persistLimitedScanResult",
    "getCustomerScanResult",
    "createAccessCheckout",
    "stripeWebhook",
    "ownerScanDebugControl",
  ];
  for (const name of expected) assert.match(deployFunctions, new RegExp(`\\b${name}\\b`));
  assert.match(deployFunctions, /functions deploy "\$\{FUNCTIONS\[@\]\}"/);
  assert.match(deployFunctions, /base44_release_manifest\.mjs" verify/);
  assert.doesNotMatch(deployFunctions, /\bdeploy\s+--|\bsite\s+deploy|entities\s+push|--force/);
  for (const source of releaseMutationScripts) assert.doesNotMatch(source, /entities\s+push/);
});

test("Base44 site publication restores the durable backend after the site deploy", () => {
  const authIndex = deploySite.indexOf('fixlist_require_base44_owner');
  const buildIndex = deploySite.indexOf('VITE_FIXLIST_SOURCE_SHA="$SOURCE_SHA" npm run build');
  const siteIndex = deploySite.indexOf('site deploy --no-build --yes');
  const functionsIndex = deploySite.indexOf('functions deploy "${FUNCTIONS[@]}"');
  const verifyIndex = deploySite.indexOf('verify-base44-site.sh');
  assert.ok(authIndex >= 0 && authIndex < buildIndex, "non-interactive auth verification must precede the build");
  assert.ok(buildIndex >= 0 && buildIndex < siteIndex, "exact source SHA must be compiled before the site deploy");
  assert.ok(siteIndex >= 0, "missing Base44 site deployment");
  assert.ok(functionsIndex > siteIndex, "release functions must deploy after the site");
  assert.ok(verifyIndex > functionsIndex, "public source verification must run after backend restoration");
  assert.equal((deploySite.match(/fixlist_require_base44_owner/g) || []).length, 1, "site publish must use one non-interactive owner check");
  assert.doesNotMatch(deploySite, /\"\$FIXLIST_BASE44_CLI\" login/);
  assert.match(mainEntry, /import\.meta\.env\.VITE_FIXLIST_SOURCE_SHA/);
  assert.match(mainEntry, /__FIXLIST_SOURCE_SHA__/);
  assert.match(verifySite, /\/assets\/index-/);
  assert.match(verifySite, /grep -Fq "\$EXPECTED_SOURCE_SHA"/);
  for (const required of [
    "startStandardScanJob",
    "durableScanWorkerControl",
    "persistDurableScanAuthority",
    "persistLimitedScanResult",
    "getCustomerScanResult",
    "createAccessCheckout",
    "stripeWebhook",
    "deleteCustomerScanData",
    "ownerScanDebugControl",
  ]) assert.match(deploySite, new RegExp(`\\b${required}\\b`));
  assert.doesNotMatch(deploySite, /deploy-base44-beta-functions\.sh|--force|entities\s+push/);
});

test("release Base44 CLI is version and digest pinned before login or deployment", () => {
  assert.match(cliHelper, /FIXLIST_BASE44_CLI_VERSION="0\.1\.8"/);
  assert.match(cliHelper, /FIXLIST_BASE44_CLI_SHA512="sha512-[A-Za-z0-9+/=]+"/);
  assert.match(cliHelper, /openssl dgst -sha512/);
  assert.match(cliHelper, /integrity mismatch/);
  assert.match(configureBase44, /fixlist_install_base44_cli/);
  assert.match(deployFunctions, /fixlist_install_base44_cli/);
});

test("exact-source guard supports shallow GitHub main checkouts without weakening identity", () => {
  assert.match(sourceGuard, /GITHUB_REF:-.*refs\/heads\/main/);
  assert.match(sourceGuard, /GITHUB_SHA/);
  assert.match(sourceGuard, /event_sha.*!=.*head/);
  assert.match(sourceGuard, /refs\/remotes\/origin\/main/);
  assert.match(sourceGuard, /remote="\$event_sha"/);
  assert.match(sourceGuard, /CONFIRM must equal exact SOURCE_SHA/);
});

test("worker candidate is exact-SHA, explicit-build-SA, private and zero-traffic", () => {
  assert.match(workerCandidate, /fixlist_require_exact_main/);
  assert.match(workerCandidate, /gcloud builds submit[\s\S]*--service-account="\$BUILD_SA_RESOURCE"/);
  assert.match(workerCandidate, /_RELEASE_SHA=\$SOURCE_SHA/);
  assert.match(workerCandidate, /FIXLIST_WORKER_SOURCE_SHA/);
  assert.match(workerCandidate, /candidate unexpectedly receives traffic/);
  assert.match(workerBuild, /--no-traffic/);
  assert.match(workerBuild, /--concurrency=1/);
  assert.match(workerBuild, /--max-instances=40/);
  assert.match(workerBuild, /FIXLIST_WORKER_SOURCE_SHA=\$\{_RELEASE_SHA\}/);
  assert.match(workerMain, /FIXLIST_WORKER_SOURCE_SHA/);
  assert.match(workerMain, /"source_sha": WORKER_SOURCE_SHA/);
});

test("gateway source deploy uses exact checkout, explicit build SA and both queues", () => {
  assert.match(gatewayDeploy, /HEAD_SHA/);
  assert.match(gatewayDeploy, /REMOTE_MAIN_SHA/);
  assert.match(gatewayDeploy, /--build-service-account="\$BUILD_SA_RESOURCE"/);
  assert.match(gatewayDeploy, /SCAN_DRAIN_QUEUE_PATH/);
  assert.match(gatewayBootstrap, /DRAIN_QUEUE="fixlist-standard150-drain"/);
  assert.ok((gatewayBootstrap.match(/roles\/cloudtasks\.enqueuer/g) || []).length >= 2);
  assert.match(gatewayBootstrap, /Allow the WIF operator to use only the resolved Cloud Build identity/);
});

test("Cloud Operator may redeploy the coordinator after bootstrap but cannot run the owner bootstrap", () => {
  assert.match(workflow, /deploy-admission-coordinator/);
  assert.match(workflow, /run: \.\/scripts\/deploy_admission_coordinator\.sh/);
  assert.doesNotMatch(workflow, /bootstrap-fixlist-admission-coordinator\.sh/);
});

test("Cloud Operator invokes the allowlisted shell through bash so file mode cannot block verification", () => {
  assert.match(workflow, /run: bash \.\/scripts\/fixlist-cloud-operator\.sh/);
});

test("credential-free release checkouts never attempt a network fetch", () => {
  for (const ownerWorkflow of [workflow, intakeWorkflow, connectivityWorkflow]) {
    assert.match(ownerWorkflow, /persist-credentials: false/);
    assert.match(ownerWorkflow, /git rev-parse origin\/main/);
    assert.doesNotMatch(ownerWorkflow, /git fetch origin main/);
  }
});

test("acceptance-only admission is exact-source, allowlisted, expiring and budget bounded", () => {
  assert.match(workflow, /- acceptance-only/);
  assert.match(workflow, /ACCEPTANCE_SOURCE_SHA: \$\{\{ github\.sha \}\}/);
  assert.match(cloudOperator, /OPEN-STANDARD150-ACCEPTANCE:\$\{SOURCE_SHA\}:\$\{BARRIER_EXPECTED_GENERATION\}:\$\{ACCEPTANCE_COHORT_ID\}/);
  assert.match(cloudOperator, /owner_user_ids/);
  assert.match(cloudOperator, /expires_at/);
  assert.match(cloudOperator, /total_claim_budget/);
  assert.match(cloudOperator, /per_owner_claim_budget/);
  assert.match(cloudOperator, /\[\[ "\$ACCEPTANCE_SOURCE_SHA" == "\$SOURCE_SHA" \]\]/);
  assert.doesNotMatch(cloudOperator, /browser.*enroll|localStorage.*cohort/i);
});

test("cutover pause drains live obligations before pausing and resume is the exact inverse", () => {
  const pause = cloudOperator.match(/cutover_pause\(\) \{[\s\S]*?\n\}/)?.[0] || "";
  const resume = cloudOperator.match(/cutover_resume\(\) \{[\s\S]*?\n\}/)?.[0] || "";
  assert.ok(pause.indexOf("call_barrier_operator close") < pause.indexOf("wait_for_barrier_drain"));
  assert.ok(pause.indexOf('pause_queue_checked "$CLOUD_TASKS_QUEUE"') < pause.indexOf('pause_queue_checked "$CLOUD_TASKS_DRAIN_QUEUE"'));
  assert.ok(pause.indexOf('pause_queue_checked "$CLOUD_TASKS_DRAIN_QUEUE"') < pause.indexOf("pause_scheduler_checked"));
  assert.ok(resume.indexOf("resume_scheduler_checked") < resume.indexOf('resume_queue_checked "$CLOUD_TASKS_DRAIN_QUEUE"'));
  assert.ok(resume.indexOf('resume_queue_checked "$CLOUD_TASKS_DRAIN_QUEUE"') < resume.indexOf('resume_queue_checked "$CLOUD_TASKS_QUEUE"'));
  assert.match(cloudOperator, /BARRIER_CLAIMED_EXPIRED="\$\{_barrier_values\[7\]\}"/);
  assert.doesNotMatch(cloudOperator.match(/require_closed_drained_barrier\(\) \{[\s\S]*?\n\}/)?.[0] || "", /CLAIMED_EXPIRED/);
});

test("Base44 intake and connectivity are isolated owner controls with no CI device login", () => {
  assert.match(intakeControl, /secrets set[\s\S]*BETA_SCAN_INTAKE_ENABLED=\$VALUE/);
  assert.doesNotMatch(intakeControl, /BETA_SCAN_ADMISSION_ENABLED=|secrets (list|delete)|"\$FIXLIST_BASE44_CLI" login/);
  assert.match(connectivityControl, /verify-zero-admission-obligations/);
  assert.match(connectivityControl, /secrets set[\s\S]*BETA_SCAN_ADMISSION_ENABLED=\$VALUE/);
  assert.doesNotMatch(connectivityControl, /BETA_SCAN_INTAKE_ENABLED=|secrets (list|delete)|"\$FIXLIST_BASE44_CLI" login/);
  for (const ownerWorkflow of [intakeWorkflow, connectivityWorkflow]) {
    assert.match(ownerWorkflow, /runs-on: \[self-hosted, fixlist-base44-owner\]/);
    assert.match(ownerWorkflow, /github\.actor == 'bright4862-design'/);
    assert.match(ownerWorkflow, /github\.ref == 'refs\/heads\/main'/);
    assert.match(ownerWorkflow, /environment: fixlist-production-owner/);
    assert.doesNotMatch(ownerWorkflow, /runs-on:\s*ubuntu-latest|BASE44_AUTH\s*:|BASE44_REFRESH_TOKEN\s*:/i);
  }
});

test("worker provenance lookup uses the same regional Cloud Build scope as the candidate build", () => {
  assert.match(
    cloudOperator,
    /gcloud builds list --project="\$GCP_PROJECT" --region="\$GCP_REGION" --limit=50/,
  );
});
