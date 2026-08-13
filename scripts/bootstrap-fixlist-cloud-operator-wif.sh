#!/usr/bin/env bash
set -euo pipefail

PROJECT="seo-autopilot-501517"
PROJECT_NUMBER="919035207432"
REGION="europe-west1"
REPO="bright4862-design/seo-autopilot"
REPO_ID="1291460209"
REPO_OWNER_ID="300628670"
MAIN_REF="refs/heads/main"
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
  --project="$PROJECT" \
  --quiet

say "Create operator service account if needed"
if ! gcloud iam service-accounts describe "$OPERATOR_SA" --project="$PROJECT" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$OPERATOR_ID" \
    --project="$PROJECT" \
    --display-name="FixList GitHub Cloud Operator" \
    --description="Keyless main-only release operator for FixList Standard 150" \
    --quiet
fi

say "Grant resource-scoped Cloud Run access"
gcloud run services add-iam-policy-binding "$WORKER" \
  --project="$PROJECT" \
  --region="$REGION" \
  --member="serviceAccount:${OPERATOR_SA}" \
  --role="roles/run.developer" \
  --quiet >/dev/null

say "Grant resource-scoped Cloud Tasks access"
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
  --quiet >/dev/null

say "Grant read-only Cloud Build provenance access"
# verify-worker-routes calls gcloud builds list. Google documents
# roles/cloudbuild.builds.viewer as the viewer role containing
# cloudbuild.builds.get/list; the lowest grant level for this role is project.
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${OPERATOR_SA}" \
  --role="roles/cloudbuild.builds.viewer" \
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

say "Create immutable-repository, owner, and main-only GitHub provider if needed"
EXPECTED_CONDITION="assertion.repository_id == '${REPO_ID}' && assertion.repository_owner_id == '${REPO_OWNER_ID}' && assertion.ref == '${MAIN_REF}'"
EXPECTED_MAPPING="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_id=assertion.repository_id,attribute.repository_owner_id=assertion.repository_owner_id,attribute.ref=assertion.ref"

if ! gcloud iam workload-identity-pools providers describe "$PROVIDER" \
  --project="$PROJECT" \
  --location=global \
  --workload-identity-pool="$POOL" >/dev/null 2>&1; then
  gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" \
    --project="$PROJECT" \
    --location=global \
    --workload-identity-pool="$POOL" \
    --display-name="FixList GitHub main" \
    --issuer-uri="https://token.actions.githubusercontent.com/" \
    --attribute-mapping="$EXPECTED_MAPPING" \
    --attribute-condition="$EXPECTED_CONDITION" \
    --quiet
else
  ACTUAL_CONDITION="$(gcloud iam workload-identity-pools providers describe "$PROVIDER" \
    --project="$PROJECT" \
    --location=global \
    --workload-identity-pool="$POOL" \
    --format='value(attributeCondition)')"
  if [[ "$ACTUAL_CONDITION" != "$EXPECTED_CONDITION" ]]; then
    echo "ERROR: existing WIF provider condition does not match the expected immutable main-only condition." >&2
    echo "Expected: $EXPECTED_CONDITION" >&2
    echo "Actual:   $ACTUAL_CONDITION" >&2
    exit 2
  fi
fi

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
printf '\nWIF_BOOTSTRAP_COMPLETE\n'
printf 'No service-account key was created. No GitHub repository secret is required for these identifiers.\n'
