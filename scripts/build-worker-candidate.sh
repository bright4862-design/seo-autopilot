#!/usr/bin/env bash
set -euo pipefail

PROJECT="${GCP_PROJECT:-seo-autopilot-501517}"
REGION="${GCP_REGION:-europe-west1}"
WORKER="${CLOUD_RUN_SERVICE:-fixlist-standard150-worker}"
SOURCE_SHA="${SOURCE_SHA:-}"
CONFIRM="${CONFIRM:-}"
BUILD_SA_INPUT="${CLOUD_BUILD_SERVICE_ACCOUNT:-}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO_ROOT/scripts/lib/release-source-guard.sh"
fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$CONFIRM"
SOURCE_SHA="$FIXLIST_EXACT_SOURCE_SHA"

gcloud config set project "$PROJECT" >/dev/null

WORKER_JSON="$(mktemp)"; REVISIONS_JSON="$(mktemp)"; trap 'rm -f "$WORKER_JSON" "$REVISIONS_JSON"' EXIT
gcloud run services describe "$WORKER" --project="$PROJECT" --region="$REGION" --format=json > "$WORKER_JSON"

readarray -t VALUES < <(python3 - "$WORKER_JSON" <<'PY'
import json,sys,re
v=json.load(open(sys.argv[1])); spec=v.get('spec',{}).get('template',{}).get('spec',{}); c=(spec.get('containers') or [{}])[0]
image=str(c.get('image') or '')
if not image: raise SystemExit('worker image missing')
base=image.split('@',1)[0]
last=base.rsplit('/',1)[-1]
if ':' in last: base=base.rsplit(':',1)[0]
env={i.get('name'):i for i in c.get('env',[])}
def val(k): return str(env.get(k,{}).get('value') or '')
ref=env.get('SCAN_EVIDENCE_SIGNING_KEY',{}).get('valueFrom',{}).get('secretKeyRef',{})
secret=str(ref.get('name') or ''); version=str(ref.get('key') or '')
items=[base,str(spec.get('serviceAccountName') or ''),val('TASKS_INVOKER_SERVICE_ACCOUNT'),val('BASE44_APP_ID'),val('BASE44_API_URL'),secret,version]
if any(not x for x in items) or not version.isdigit(): raise SystemExit('worker deployment inputs incomplete')
for x in items: print(x)
PY
)
IMAGE="${VALUES[0]}"; RUNTIME_SA="${VALUES[1]}"; INVOKER_SA="${VALUES[2]}"; BASE44_APP="${VALUES[3]}"; BASE44_API="${VALUES[4]}"; SIGNING_SECRET="${VALUES[5]}"; SIGNING_VERSION="${VALUES[6]}"

normalize_build_sa() {
  local raw="$1"; raw="${raw##*/}"
  [[ "$raw" == *@* ]] || { echo "Invalid Cloud Build service account." >&2; exit 2; }
  BUILD_SA_EMAIL="$raw"; BUILD_SA_RESOURCE="projects/${PROJECT}/serviceAccounts/${raw}"
}
if [[ -n "$BUILD_SA_INPUT" ]]; then normalize_build_sa "$BUILD_SA_INPUT"; else normalize_build_sa "$(gcloud builds get-default-service-account --project="$PROJECT" --format='value(serviceAccountEmail)')"; fi
gcloud iam service-accounts describe "$BUILD_SA_EMAIL" --project="$PROJECT" >/dev/null

printf 'worker=%s\nimage=%s\nruntime_sa=%s\ninvoker_sa=%s\nbuild_sa=%s\nsource_sha=%s\n' \
  "$WORKER" "$IMAGE" "$RUNTIME_SA" "$INVOKER_SA" "$BUILD_SA_EMAIL" "$SOURCE_SHA"

gcloud builds submit "$REPO_ROOT" \
  --project="$PROJECT" \
  --region="$REGION" \
  --config="$REPO_ROOT/cloudbuild.durable-worker.yaml" \
  --service-account="$BUILD_SA_RESOURCE" \
  --substitutions="_RELEASE_SHA=$SOURCE_SHA,_WORKER_SERVICE=$WORKER,_REGION=$REGION,_IMAGE=$IMAGE,_RUNTIME_SA=$RUNTIME_SA,_INVOKER_SA=$INVOKER_SA,_BASE44_APP_ID=$BASE44_APP,_BASE44_API_URL=$BASE44_API,_SIGNING_KEY_SECRET=$SIGNING_SECRET,_SIGNING_KEY_VERSION=$SIGNING_VERSION"

gcloud run revisions list --service="$WORKER" --project="$PROJECT" --region="$REGION" --format=json > "$REVISIONS_JSON"
CANDIDATE="$(python3 - "$REVISIONS_JSON" "$SOURCE_SHA" <<'PY'
import json,sys
rows=json.load(open(sys.argv[1])); sha=sys.argv[2]
for r in rows:
  spec=r.get('spec',{}); c=(spec.get('containers') or [{}])[0]; env={i.get('name'):i.get('value','') for i in c.get('env',[])}
  if env.get('FIXLIST_WORKER_SOURCE_SHA')==sha:
    print(r.get('metadata',{}).get('name','')); break
PY
)"
[[ -n "$CANDIDATE" ]] || { echo "No worker revision carries FIXLIST_WORKER_SOURCE_SHA=$SOURCE_SHA" >&2; exit 2; }

gcloud run revisions describe "$CANDIDATE" --project="$PROJECT" --region="$REGION" --format=json > "$REVISIONS_JSON"
python3 - "$REVISIONS_JSON" "$SOURCE_SHA" <<'PY'
import json,sys
v=json.load(open(sys.argv[1])); sha=sys.argv[2]; spec=v.get('spec',{}); c=(spec.get('containers') or [{}])[0]
env={i.get('name'):i.get('value','') for i in c.get('env',[])}
if env.get('FIXLIST_WORKER_SOURCE_SHA')!=sha: raise SystemExit('candidate source SHA mismatch')
if int(spec.get('containerConcurrency') or 0)!=1: raise SystemExit('candidate concurrency is not 1')
if int(spec.get('timeoutSeconds') or 0)!=480: raise SystemExit('candidate timeout is not 480')
conds=v.get('status',{}).get('conditions',[])
ready=next((x for x in conds if x.get('type')=='Ready'),{})
if str(ready.get('status') or '').lower()!='true': raise SystemExit('candidate revision is not Ready')
PY

SERVICE_JSON="$(mktemp)"; trap 'rm -f "$WORKER_JSON" "$REVISIONS_JSON" "$SERVICE_JSON"' EXIT
gcloud run services describe "$WORKER" --project="$PROJECT" --region="$REGION" --format=json > "$SERVICE_JSON"
python3 - "$SERVICE_JSON" "$CANDIDATE" <<'PY'
import json,sys
v=json.load(open(sys.argv[1])); candidate=sys.argv[2]
for item in v.get('status',{}).get('traffic',[]) or []:
  if item.get('revisionName')==candidate and int(item.get('percent') or 0)>0:
    raise SystemExit('candidate unexpectedly receives traffic')
print('Candidate traffic verified at 0%.')
PY
printf 'WORKER_CANDIDATE_READY=%s\nWORKER_CANDIDATE_SOURCE_SHA=%s\n' "$CANDIDATE" "$SOURCE_SHA"
