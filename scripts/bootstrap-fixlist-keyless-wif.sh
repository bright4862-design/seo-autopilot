#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="seo-autopilot-501517"
PROJECT_NUMBER="919035207432"
REGION="europe-west1"
REPO="bright4862-design/seo-autopilot"
REPO_ID="1291460209"
REPO_OWNER_ID="300628670"
RECOVERY_REF="refs/heads/agent/fixlist-keyless-recovery"
POOL_ID="fixlist-github"
PROVIDER_ID="github"
OPERATOR_SA="fixlist-github-cloud-operator@${PROJECT_ID}.iam.gserviceaccount.com"
OPERATOR_SA_ID="fixlist-github-cloud-operator"
GATEWAY_RUNTIME_SA="fixlist-base44-dispatcher@${PROJECT_ID}.iam.gserviceaccount.com"
TASKS_INVOKER_SA="fixlist-standard150-invoker@${PROJECT_ID}.iam.gserviceaccount.com"
WORKER_SERVICE="fixlist-standard150-worker"
QUEUE="fixlist-standard150"
COMPUTE_BUILD_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

POOL_NAME="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}"
PROVIDER_NAME="${POOL_NAME}/providers/${PROVIDER_ID}"
REPO_PRINCIPAL="principalSet://iam.googleapis.com/${POOL_NAME}/attribute.repository_id/${REPO_ID}"

say() { printf '\n==> %s\n' "$*"; }

say "Selecting project"
gcloud config set project "$PROJECT_ID" >/dev/null

say "Enabling only the APIs required for keyless GitHub federation"
gcloud services enable \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  sts.googleapis.com \
  --project="$PROJECT_ID" \
  --quiet

say "Verifying existing FixList service accounts"
gcloud iam service-accounts describe "$GATEWAY_RUNTIME_SA" --project="$PROJECT_ID" >/dev/null
gcloud iam service-accounts describe "$TASKS_INVOKER_SA" --project="$PROJECT_ID" >/dev/null

say "Creating Workload Identity Pool if absent"
if ! gcloud iam workload-identity-pools describe "$POOL_ID" \
  --project="$PROJECT_ID" \
  --location=global >/dev/null 2>&1; then
  gcloud iam workload-identity-pools create "$POOL_ID" \
    --project="$PROJECT_ID" \
    --location=global \
    --display-name="FixList GitHub Actions" \
    --description="Keyless GitHub Actions identity for FixList release automation" \
    --quiet
fi

say "Creating immutable-repository- and branch-restricted GitHub OIDC provider if absent"
if ! gcloud iam workload-identity-pools providers describe "$PROVIDER_ID" \
  --project="$PROJECT_ID" \
  --location=global \
  --workload-identity-pool="$POOL_ID" >/dev/null 2>&1; then
  gcloud iam workload-identity-pools providers create-oidc "$PROVIDER_ID" \
    --project="$PROJECT_ID" \
    --location=global \
    --workload-identity-pool="$POOL_ID" \
    --display-name="FixList GitHub recovery" \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository,attribute.repository_id=assertion.repository_id,attribute.repository_owner_id=assertion.repository_owner_id,attribute.ref=assertion.ref,attribute.event_name=assertion.event_name" \
    --attribute-condition="assertion.repository_id == '${REPO_ID}' && assertion.repository_owner_id == '${REPO_OWNER_ID}' && assertion.ref == '${RECOVERY_REF}' && assertion.event_name == 'push'" \
    --quiet
fi

say "Verifying exact provider configuration"
ACTUAL_PROVIDER="$(gcloud iam workload-identity-pools providers describe "$PROVIDER_ID" \
  --project="$PROJECT_ID" \
  --location=global \
  --workload-identity-pool="$POOL_ID" \
  --format='value(name)')"
test "$ACTUAL_PROVIDER" = "$PROVIDER_NAME"

gcloud iam workload-identity-pools providers describe "$PROVIDER_ID" \
  --project="$PROJECT_ID" \
  --location=global \
  --workload-identity-pool="$POOL_ID" \
  --format='yaml(name,state,attributeMapping,attributeCondition,oidc.issuerUri)'

say "Creating dedicated GitHub operator service account if absent"
if ! gcloud iam service-accounts describe "$OPERATOR_SA" --project="$PROJECT_ID" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$OPERATOR_SA_ID" \
    --project="$PROJECT_ID" \
    --display-name="FixList GitHub Cloud Operator" \
    --description="Keyless GitHub Actions deployer for FixList recovery" \
    --quiet
fi

say "Allowing only the immutable repository principal to impersonate the operator"
gcloud iam service-accounts add-iam-policy-binding "$OPERATOR_SA" \
  --project="$PROJECT_ID" \
  --role="roles/iam.workloadIdentityUser" \
  --member="$REPO_PRINCIPAL" \
  --quiet >/dev/null

say "Granting temporary recovery deploy permissions to the GitHub operator"
# Source deploy requires run.sourceDeveloper + serviceUsageConsumer. Configuring
# the gateway's Secret Manager reference and public IAM requires run.admin.
# These operator grants are bootstrap/recovery grants and should be narrowed or
# removed after the gateway is verified and production is stable.
for ROLE in \
  roles/run.admin \
  roles/run.sourceDeveloper \
  roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${OPERATOR_SA}" \
    --role="$ROLE" \
    --quiet >/dev/null
done

say "Allowing the operator to attach only the gateway runtime identity"
gcloud iam service-accounts add-iam-policy-binding "$GATEWAY_RUNTIME_SA" \
  --project="$PROJECT_ID" \
  --member="serviceAccount:${OPERATOR_SA}" \
  --role="roles/iam.serviceAccountUser" \
  --quiet >/dev/null

say "Ensuring the Cloud Run source-build identity has the documented builder role"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${COMPUTE_BUILD_SA}" \
  --role="roles/run.builder" \
  --quiet >/dev/null

say "Granting the gateway runtime access only to the Standard 150 queue"
gcloud tasks queues add-iam-policy-binding "$QUEUE" \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --member="serviceAccount:${GATEWAY_RUNTIME_SA}" \
  --role="roles/cloudtasks.enqueuer" \
  --quiet >/dev/null

say "Allowing the gateway runtime to use only the existing task OIDC identity"
gcloud iam service-accounts add-iam-policy-binding "$TASKS_INVOKER_SA" \
  --project="$PROJECT_ID" \
  --member="serviceAccount:${GATEWAY_RUNTIME_SA}" \
  --role="roles/iam.serviceAccountUser" \
  --quiet >/dev/null

say "Resolving the existing worker signing-secret reference without reading secret data"
WORKER_JSON="$(mktemp)"
trap 'rm -f "$WORKER_JSON"' EXIT
gcloud run services describe "$WORKER_SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format=json > "$WORKER_JSON"

read -r SIGNING_SECRET SIGNING_VERSION < <(python3 - "$WORKER_JSON" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    service = json.load(handle)
containers = service.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
if not containers:
    raise SystemExit("existing worker has no container configuration")
for item in containers[0].get("env", []):
    if item.get("name") != "SCAN_EVIDENCE_SIGNING_KEY":
        continue
    ref = item.get("valueFrom", {}).get("secretKeyRef", {})
    name = str(ref.get("name") or "").strip()
    version = str(ref.get("key") or "").strip()
    if not name or not version:
        raise SystemExit("existing signing-secret reference is incomplete")
    print(name, version)
    break
else:
    raise SystemExit("existing worker does not reference SCAN_EVIDENCE_SIGNING_KEY")
PY
)

test -n "$SIGNING_SECRET"
test -n "$SIGNING_VERSION"
printf 'Signing secret reference: %s:%s (value was not read)\n' "$SIGNING_SECRET" "$SIGNING_VERSION"

say "Granting the gateway runtime access only to that existing secret"
gcloud secrets add-iam-policy-binding "$SIGNING_SECRET" \
  --project="$PROJECT_ID" \
  --member="serviceAccount:${GATEWAY_RUNTIME_SA}" \
  --role="roles/secretmanager.secretAccessor" \
  --quiet >/dev/null

say "Final read-only verification"
printf 'Provider: %s\n' "$PROVIDER_NAME"
printf 'Operator: %s\n' "$OPERATOR_SA"
printf 'Repository: %s (id=%s, owner_id=%s)\n' "$REPO" "$REPO_ID" "$REPO_OWNER_ID"
printf 'Repository principal: %s\n' "$REPO_PRINCIPAL"
printf 'Gateway runtime: %s\n' "$GATEWAY_RUNTIME_SA"
printf 'Queue: projects/%s/locations/%s/queues/%s\n' "$PROJECT_ID" "$REGION" "$QUEUE"
printf 'Signing secret reference: %s:%s\n' "$SIGNING_SECRET" "$SIGNING_VERSION"

gcloud iam service-accounts get-iam-policy "$OPERATOR_SA" \
  --project="$PROJECT_ID" \
  --format='yaml(bindings)'

echo
printf '%s\n' "WIF_BOOTSTRAP_COMPLETE"
printf '%s\n' "Wait up to 5 minutes for IAM/WIF propagation before re-running GitHub authentication."
