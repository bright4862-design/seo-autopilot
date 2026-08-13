#!/usr/bin/env bash
set -euo pipefail

PROJECT="seo-autopilot-501517"
PROJECT_NUMBER="919035207432"
REGION="europe-west1"
RELEASE_OPERATOR_SA="fixlist-release-operator@${PROJECT}.iam.gserviceaccount.com"
WIF_OPERATOR_SA="fixlist-github-operator@${PROJECT}.iam.gserviceaccount.com"
WORKER="fixlist-standard150-worker"
GATEWAY="fixlist-dispatch-gateway"
QUEUE="fixlist-standard150"
INVOKER_SA="fixlist-standard150-invoker@${PROJECT}.iam.gserviceaccount.com"
GATEWAY_RUNTIME_SA="fixlist-base44-dispatcher@${PROJECT}.iam.gserviceaccount.com"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

say() { printf '\n==> %s\n' "$*"; }

say "Verify clean current origin/main"
git -C "$REPO_ROOT" fetch origin main --quiet
LOCAL_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD)"
REMOTE_SHA="$(git -C "$REPO_ROOT" rev-parse origin/main)"
if [[ "$LOCAL_SHA" != "$REMOTE_SHA" ]]; then
  echo "Refusing bootstrap: checkout $LOCAL_SHA is not current origin/main $REMOTE_SHA" >&2
  exit 2
fi
if [[ -n "$(git -C "$REPO_ROOT" status --porcelain --untracked-files=all)" ]]; then
  echo "Refusing bootstrap: repository is not clean." >&2
  exit 2
fi
printf 'source_sha=%s\n' "$LOCAL_SHA"

gcloud config set project "$PROJECT" >/dev/null

say "Enable Agent Engine and operator APIs"
gcloud services enable \
  aiplatform.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  run.googleapis.com \
  cloudtasks.googleapis.com \
  cloudbuild.googleapis.com \
  logging.googleapis.com \
  secretmanager.googleapis.com \
  --project="$PROJECT" \
  --quiet

say "Ensure Agent Engine service identity exists"
gcloud beta services identity create \
  --service=aiplatform.googleapis.com \
  --project="$PROJECT" >/dev/null 2>&1 || true

say "Create dedicated release operator service account if needed"
if ! gcloud iam service-accounts describe "$RELEASE_OPERATOR_SA" --project="$PROJECT" >/dev/null 2>&1; then
  gcloud iam service-accounts create fixlist-release-operator \
    --project="$PROJECT" \
    --display-name="FixList Release Operator" \
    --description="Dedicated runtime identity for the allowlisted FixList Standard 150 release operator"
fi

say "Grant only project-level read/use roles required by the release agent"
for ROLE in \
  roles/aiplatform.user \
  roles/serviceusage.serviceUsageConsumer \
  roles/logging.viewer \
  roles/cloudbuild.builds.viewer; do
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:${RELEASE_OPERATOR_SA}" \
    --role="$ROLE" \
    --condition=None \
    --quiet >/dev/null
done

say "Grant Cloud Run Admin only on the two FixList release services"
for SERVICE in "$WORKER" "$GATEWAY"; do
  gcloud run services add-iam-policy-binding "$SERVICE" \
    --project="$PROJECT" \
    --region="$REGION" \
    --member="serviceAccount:${RELEASE_OPERATOR_SA}" \
    --role="roles/run.admin" \
    --condition=None \
    --quiet >/dev/null
done

say "Grant queue administration and task inspection only on Standard 150"
for ROLE in roles/cloudtasks.queueAdmin roles/cloudtasks.viewer; do
  gcloud tasks queues add-iam-policy-binding "$QUEUE" \
    --project="$PROJECT" \
    --location="$REGION" \
    --member="serviceAccount:${RELEASE_OPERATOR_SA}" \
    --role="$ROLE" \
    --quiet >/dev/null
done

say "Allow the release operator to attach only existing FixList runtime identities"
for TARGET_SA in "$INVOKER_SA" "$GATEWAY_RUNTIME_SA" "$RELEASE_OPERATOR_SA"; do
  gcloud iam service-accounts add-iam-policy-binding "$TARGET_SA" \
    --project="$PROJECT" \
    --member="serviceAccount:${RELEASE_OPERATOR_SA}" \
    --role="roles/iam.serviceAccountUser" \
    --condition=None \
    --quiet >/dev/null
done

# Resolve the worker runtime identity rather than guessing it.
WORKER_RUNTIME_SA="$(gcloud run services describe "$WORKER" \
  --project="$PROJECT" \
  --region="$REGION" \
  --format='value(spec.template.spec.serviceAccountName)')"
if [[ -z "$WORKER_RUNTIME_SA" || "$WORKER_RUNTIME_SA" != *@* ]]; then
  echo "Could not resolve worker runtime service account." >&2
  exit 3
fi
gcloud iam service-accounts add-iam-policy-binding "$WORKER_RUNTIME_SA" \
  --project="$PROJECT" \
  --member="serviceAccount:${RELEASE_OPERATOR_SA}" \
  --role="roles/iam.serviceAccountUser" \
  --condition=None \
  --quiet >/dev/null

say "Grant access to the exact signing secret used by the live worker"
WORKER_JSON="$(mktemp)"
trap 'rm -f "$WORKER_JSON"' EXIT
gcloud run services describe "$WORKER" \
  --project="$PROJECT" \
  --region="$REGION" \
  --format=json > "$WORKER_JSON"
read -r SIGNING_SECRET SIGNING_VERSION < <(python3 - "$WORKER_JSON" <<'PY'
import json, sys
service = json.load(open(sys.argv[1]))
containers = service.get('spec', {}).get('template', {}).get('spec', {}).get('containers', [])
if not containers:
    raise SystemExit('worker container config missing')
for item in containers[0].get('env', []):
    if item.get('name') != 'SCAN_EVIDENCE_SIGNING_KEY':
        continue
    ref = item.get('valueFrom', {}).get('secretKeyRef', {})
    name = str(ref.get('name') or '').strip()
    version = str(ref.get('key') or '').strip()
    if not name or not version or version == 'latest':
        raise SystemExit('worker signing secret is not pinned')
    print(name, version)
    break
else:
    raise SystemExit('worker signing secret reference missing')
PY
)
gcloud secrets add-iam-policy-binding "$SIGNING_SECRET" \
  --project="$PROJECT" \
  --member="serviceAccount:${RELEASE_OPERATOR_SA}" \
  --role="roles/secretmanager.secretAccessor" \
  --condition=None \
  --quiet >/dev/null

say "Allow the trusted GitHub deployer to attach the release operator identity"
gcloud iam service-accounts add-iam-policy-binding "$RELEASE_OPERATOR_SA" \
  --project="$PROJECT" \
  --member="serviceAccount:${WIF_OPERATOR_SA}" \
  --role="roles/iam.serviceAccountUser" \
  --condition=None \
  --quiet >/dev/null

say "Verify broad basic roles were NOT granted"
for ROLE in roles/owner roles/editor roles/viewer roles/resourcemanager.projectIamAdmin; do
  FOUND="$(gcloud projects get-iam-policy "$PROJECT" \
    --flatten='bindings[].members' \
    --filter="bindings.role=${ROLE} AND bindings.members=serviceAccount:${RELEASE_OPERATOR_SA}" \
    --format='value(bindings.role)' | head -n 1)"
  if [[ -n "$FOUND" ]]; then
    echo "Refusing completion: release operator has prohibited broad role $ROLE" >&2
    exit 4
  fi
done

printf '\nRELEASE_OPERATOR_BOOTSTRAP_COMPLETE\n'
printf 'release_operator=%s\n' "$RELEASE_OPERATOR_SA"
printf 'worker_runtime=%s\n' "$WORKER_RUNTIME_SA"
printf 'signing_secret_ref=%s:%s (value not read)\n' "$SIGNING_SECRET" "$SIGNING_VERSION"
printf 'No service-account key was created.\n'
