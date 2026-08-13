#!/usr/bin/env bash
set -euo pipefail

PROJECT="seo-autopilot-501517"
PROJECT_NUMBER="919035207432"
REGION="europe-west1"
REPO="bright4862-design/seo-autopilot"
REPO_ID="1291460209"
REPO_OWNER_ID="300628670"
MAIN_REF="refs/heads/main"
WORKFLOW_REF="${REPO}/.github/workflows/fixlist-cloud-operator.yml@${MAIN_REF}"
POOL="github"
PROVIDER="github-actions"
OPERATOR_ID="fixlist-github-operator"
OPERATOR_SA="${OPERATOR_ID}@${PROJECT}.iam.gserviceaccount.com"
WORKER="fixlist-standard150-worker"
QUEUE="fixlist-standard150"
INVOKER_SA="fixlist-standard150-invoker@${PROJECT}.iam.gserviceaccount.com"

say() { printf '\n==> %s\n' "$*"; }

gcloud config set project "$PROJECT" >/dev/null

say "Enable WIF APIs"
gcloud services enable \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  sts.googleapis.com \
  cloudresourcemanager.googleapis.com \
  --project="$PROJECT" \
  --quiet

say "Create operator service account if needed"
if ! gcloud iam service-accounts describe "$OPERATOR_SA" --project="$PROJECT" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$OPERATOR_ID" \
    --project="$PROJECT" \
    --display-name="FixList GitHub Cloud Operator" \
    --description="Keyless exact-workflow release operator for FixList Standard 150" \
    --quiet
fi

say "Grant resource-scoped Cloud Run access"
gcloud run services add-iam-policy-binding "$WORKER" \
  --project="$PROJECT" \
  --region="$REGION" \
  --member="serviceAccount:${OPERATOR_SA}" \
  --role="roles/run.developer" \
  --condition=None \
  --quiet >/dev/null

say "Grant resource-scoped Cloud Tasks access"
# The GA Cloud Tasks queue IAM command does not expose --condition in all
# installed gcloud releases. Queue bindings here are intentionally unconditional.
gcloud tasks queues add-iam-policy-binding "$QUEUE" \
  --project="$PROJECT" \
  --location="$REGION" \
  --member="serviceAccount:${OPERATOR_SA}" \
  --role="roles/cloudtasks.queueAdmin" \
  --quiet >/dev/null

say "Grant read-only visibility of the task invoker service account"
gcloud iam service-accounts add-iam-policy-binding "$INVOKER_SA" \
  --project="$PROJECT" \
  --member="serviceAccount:${OPERATOR_SA}" \
  --role="roles/iam.serviceAccountViewer" \
  --condition=None \
  --quiet >/dev/null

say "Grant read-only Cloud Build provenance access"
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${OPERATOR_SA}" \
  --role="roles/cloudbuild.builds.viewer" \
  --condition=None \
  --quiet >/dev/null

say "Create WIF pool if needed"
if ! gcloud iam workload-identity-pools describe "$POOL" \
  --project="$PROJECT" --location=global >/dev/null 2>&1; then
  gcloud iam workload-identity-pools create "$POOL" \
    --project="$PROJECT" \
    --location=global \
    --display-name="FixList GitHub Actions" \
    --description="Keyless GitHub Actions identity for FixList" \
    --quiet
fi

say "Create immutable repository, main, and exact-workflow GitHub provider if needed"
EXPECTED_CONDITION="assertion.repository_id == '${REPO_ID}' && assertion.repository_owner_id == '${REPO_OWNER_ID}' && assertion.ref == '${MAIN_REF}' && assertion.workflow_ref == '${WORKFLOW_REF}'"
EXPECTED_MAPPING="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_id=assertion.repository_id,attribute.repository_owner_id=assertion.repository_owner_id,attribute.ref=assertion.ref,attribute.workflow_ref=assertion.workflow_ref"

if ! gcloud iam workload-identity-pools providers describe "$PROVIDER" \
  --project="$PROJECT" \
  --location=global \
  --workload-identity-pool="$POOL" >/dev/null 2>&1; then
  gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" \
    --project="$PROJECT" \
    --location=global \
    --workload-identity-pool="$POOL" \
    --display-name="FixList GitHub main operator" \
    --issuer-uri="https://token.actions.githubusercontent.com/" \
    --attribute-mapping="$EXPECTED_MAPPING" \
    --attribute-condition="$EXPECTED_CONDITION" \
    --quiet
fi

PROVIDER_JSON="$(mktemp)"
trap 'rm -f "$PROVIDER_JSON"' EXIT
gcloud iam workload-identity-pools providers describe "$PROVIDER" \
  --project="$PROJECT" \
  --location=global \
  --workload-identity-pool="$POOL" \
  --format=json > "$PROVIDER_JSON"

python3 - "$PROVIDER_JSON" "$EXPECTED_CONDITION" "$WORKFLOW_REF" <<'PY'
import json, sys
path, expected_condition, expected_workflow = sys.argv[1:4]
with open(path, encoding="utf-8") as fh:
    data = json.load(fh)
if data.get("state") != "ACTIVE":
    raise SystemExit(f"WIF provider is not ACTIVE: {data.get('state')!r}")
issuer = str(data.get("oidc", {}).get("issuerUri") or "").rstrip("/")
if issuer != "https://token.actions.githubusercontent.com":
    raise SystemExit(f"Unexpected GitHub issuer: {issuer!r}")
if data.get("attributeCondition") != expected_condition:
    raise SystemExit("Existing WIF provider condition does not match the exact immutable workflow condition")
mapping = data.get("attributeMapping") or {}
expected = {
    "google.subject": "assertion.sub",
    "attribute.repository": "assertion.repository",
    "attribute.repository_id": "assertion.repository_id",
    "attribute.repository_owner_id": "assertion.repository_owner_id",
    "attribute.ref": "assertion.ref",
    "attribute.workflow_ref": "assertion.workflow_ref",
}
for key, value in expected.items():
    if mapping.get(key) != value:
        raise SystemExit(f"Unexpected attribute mapping for {key}: {mapping.get(key)!r}")
print(f"Exact workflow trust verified: {expected_workflow}")
PY

POOL_NAME="$(gcloud iam workload-identity-pools describe "$POOL" \
  --project="$PROJECT" \
  --location=global \
  --format='value(name)')"
PROVIDER_NAME="${POOL_NAME}/providers/${PROVIDER}"
PRINCIPAL="principalSet://iam.googleapis.com/${POOL_NAME}/attribute.repository_id/${REPO_ID}"

say "Allow only this immutable repository identity to impersonate the operator"
gcloud iam service-accounts add-iam-policy-binding "$OPERATOR_SA" \
  --project="$PROJECT" \
  --member="$PRINCIPAL" \
  --role="roles/iam.workloadIdentityUser" \
  --condition=None \
  --quiet >/dev/null

say "Verify exact WIF configuration"
gcloud iam workload-identity-pools providers describe "$PROVIDER" \
  --project="$PROJECT" \
  --location=global \
  --workload-identity-pool="$POOL" \
  --format='yaml(name,state,attributeMapping,attributeCondition,oidc.issuerUri)'

printf '\nWIF_PROVIDER=%s\n' "$PROVIDER_NAME"
printf 'OPERATOR_SA=%s\n' "$OPERATOR_SA"
printf 'REPOSITORY=%s (id=%s owner_id=%s)\n' "$REPO" "$REPO_ID" "$REPO_OWNER_ID"
printf 'AUTHORIZED_REF=%s\n' "$MAIN_REF"
printf 'AUTHORIZED_WORKFLOW=%s\n' "$WORKFLOW_REF"
printf '\nWIF_BOOTSTRAP_COMPLETE\n'
printf 'No service-account key was created. No GitHub repository secret is required for these identifiers.\n'
