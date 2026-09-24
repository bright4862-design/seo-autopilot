#!/usr/bin/env bash
set -euo pipefail

PROJECT="${GCP_PROJECT:-seo-autopilot-501517}"
REGION="${GCP_REGION:-europe-west1}"
WORKER="${CLOUD_RUN_SERVICE:-fixlist-standard150-worker}"
SOURCE_SHA="${SOURCE_SHA:-}"
CONFIRM="${CONFIRM:-}"
BUILD_SA_INPUT="${CLOUD_BUILD_SERVICE_ACCOUNT:-}"
EGRESS_MODE="${FIXLIST_EGRESS_MODE:-none}"
EGRESS_NETWORK="${FIXLIST_EGRESS_NETWORK:-}"
EGRESS_SUBNET="${FIXLIST_EGRESS_SUBNET:-}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO_ROOT/scripts/lib/release-source-guard.sh"
fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$CONFIRM"
SOURCE_SHA="$FIXLIST_EXACT_SOURCE_SHA"

case "$EGRESS_MODE" in
  none)
    [[ -z "$EGRESS_NETWORK" && -z "$EGRESS_SUBNET" ]] || {
      echo "Refusing: network/subnet supplied while FIXLIST_EGRESS_MODE=none." >&2
      exit 2
    }
    ;;
  static-canary)
    [[ "$EGRESS_NETWORK" == "fixlist-scanner-egress" ]] || {
      echo "Refusing: unexpected static-egress canary network." >&2
      exit 2
    }
    [[ "$EGRESS_SUBNET" == "fixlist-scanner-egress-euw1" ]] || {
      echo "Refusing: unexpected static-egress canary subnet." >&2
      exit 2
    }
    "$REPO_ROOT/scripts/verify-fixlist-static-egress-canary.sh" >/dev/null
    ;;
  *)
    echo "Refusing unsupported FIXLIST_EGRESS_MODE=$EGRESS_MODE." >&2
    exit 2
    ;;
esac

gcloud config set project "$PROJECT" >/dev/null

WORKER_JSON="$(mktemp)"
REVISIONS_JSON="$(mktemp)"
SERVICE_JSON="$(mktemp)"
BUILD_CONTEXT="$(mktemp -d)"
cleanup() {
  rm -f "$WORKER_JSON" "$REVISIONS_JSON" "$SERVICE_JSON"
  rm -rf "$BUILD_CONTEXT"
}
trap cleanup EXIT

gcloud run services describe "$WORKER" --project="$PROJECT" --region="$REGION" --format=json > "$WORKER_JSON"

readarray -t VALUES < <(python3 - "$WORKER_JSON" <<'PY'
import json,sys
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

printf 'worker=%s\nimage=%s\nruntime_sa=%s\ninvoker_sa=%s\nbuild_sa=%s\nsource_sha=%s\negress_mode=%s\n' \
  "$WORKER" "$IMAGE" "$RUNTIME_SA" "$INVOKER_SA" "$BUILD_SA_EMAIL" "$SOURCE_SHA" "$EGRESS_MODE"

# Submit only a clean archive of the exact verified commit. The generated stamp
# is provenance metadata consumed by cloudbuild.durable-worker.yaml and is not
# copied into the worker image.
git -C "$REPO_ROOT" archive --format=tar "$SOURCE_SHA" | tar -xf - -C "$BUILD_CONTEXT"
printf '%s\n' "$SOURCE_SHA" > "$BUILD_CONTEXT/.fixlist-source-sha"

gcloud builds submit "$BUILD_CONTEXT" \
  --project="$PROJECT" \
  --region="$REGION" \
  --config="$BUILD_CONTEXT/cloudbuild.durable-worker.yaml" \
  --service-account="$BUILD_SA_RESOURCE" \
  --substitutions="_RELEASE_SHA=$SOURCE_SHA,_WORKER_SERVICE=$WORKER,_REGION=$REGION,_IMAGE=$IMAGE,_RUNTIME_SA=$RUNTIME_SA,_INVOKER_SA=$INVOKER_SA,_BASE44_APP_ID=$BASE44_APP,_BASE44_API_URL=$BASE44_API,_SIGNING_KEY_SECRET=$SIGNING_SECRET,_SIGNING_KEY_VERSION=$SIGNING_VERSION,_EGRESS_MODE=$EGRESS_MODE,_EGRESS_NETWORK=$EGRESS_NETWORK,_EGRESS_SUBNET=$EGRESS_SUBNET"

gcloud run revisions list --service="$WORKER" --project="$PROJECT" --region="$REGION" --format=json > "$REVISIONS_JSON"
CANDIDATE="$(python3 - "$REVISIONS_JSON" "$SOURCE_SHA" "$EGRESS_MODE" "$EGRESS_NETWORK" "$EGRESS_SUBNET" <<'PY'
import json, sys
rows=json.load(open(sys.argv[1])); sha, mode, network, subnet = sys.argv[2:]
matches=[]
for r in rows:
  spec=r.get('spec',{}); c=(spec.get('containers') or [{}])[0]
  env={i.get('name'):i.get('value','') for i in c.get('env',[])}
  if env.get('FIXLIST_WORKER_SOURCE_SHA') != sha or env.get('FIXLIST_EGRESS_MODE','none') != mode:
    continue
  annotations=r.get('metadata',{}).get('annotations',{}) or {}
  raw=annotations.get('run.googleapis.com/network-interfaces','')
  if mode == 'static-canary':
    try:
      interfaces=json.loads(raw)
    except Exception:
      continue
    if len(interfaces)!=1:
      continue
    item=interfaces[0]
    if str(item.get('network','')).split('/')[-1] != network or str(item.get('subnetwork','')).split('/')[-1] != subnet:
      continue
    if annotations.get('run.googleapis.com/vpc-access-egress') != 'all-traffic':
      continue
  else:
    if raw:
      continue
  matches.append((r.get('metadata',{}).get('creationTimestamp',''), r.get('metadata',{}).get('name','')))
matches.sort()
print(matches[-1][1] if matches else '')
PY
)"
[[ -n "$CANDIDATE" ]] || { echo "No worker revision carries FIXLIST_WORKER_SOURCE_SHA=$SOURCE_SHA" >&2; exit 2; }

gcloud run revisions describe "$CANDIDATE" --project="$PROJECT" --region="$REGION" --format=json > "$REVISIONS_JSON"
python3 - "$REVISIONS_JSON" "$SOURCE_SHA" "$EGRESS_MODE" "$EGRESS_NETWORK" "$EGRESS_SUBNET" <<'PY'
import json, sys
v=json.load(open(sys.argv[1])); sha, mode, network, subnet = sys.argv[2:]
spec=v.get('spec',{}); c=(spec.get('containers') or [{}])[0]
env={i.get('name'):i.get('value','') for i in c.get('env',[])}
if env.get('FIXLIST_WORKER_SOURCE_SHA')!=sha: raise SystemExit('candidate source SHA mismatch')
if env.get('FIXLIST_EGRESS_MODE','none')!=mode: raise SystemExit('candidate egress mode mismatch')
if int(spec.get('containerConcurrency') or 0)!=1: raise SystemExit('candidate concurrency is not 1')
if int(spec.get('timeoutSeconds') or 0)!=480: raise SystemExit('candidate timeout is not 480')
annotations=v.get('metadata',{}).get('annotations',{}) or {}
raw=annotations.get('run.googleapis.com/network-interfaces','')
if mode == 'static-canary':
    try: interfaces=json.loads(raw)
    except Exception: raise SystemExit('candidate direct-VPC annotation is invalid')
    if len(interfaces)!=1: raise SystemExit('candidate must have exactly one direct-VPC interface')
    item=interfaces[0]
    if str(item.get('network','')).split('/')[-1] != network: raise SystemExit('candidate network mismatch')
    if str(item.get('subnetwork','')).split('/')[-1] != subnet: raise SystemExit('candidate subnet mismatch')
    if annotations.get('run.googleapis.com/vpc-access-egress') != 'all-traffic': raise SystemExit('candidate VPC egress is not all-traffic')
elif raw:
    raise SystemExit('normal candidate unexpectedly uses Direct VPC')
conds=v.get('status',{}).get('conditions',[])
ready=next((x for x in conds if x.get('type')=='Ready'),{})
if str(ready.get('status') or '').lower()!='true': raise SystemExit('candidate revision is not Ready')
PY

gcloud run services describe "$WORKER" --project="$PROJECT" --region="$REGION" --format=json > "$SERVICE_JSON"
python3 - "$SERVICE_JSON" "$CANDIDATE" <<'PY'
import json,sys
v=json.load(open(sys.argv[1])); candidate=sys.argv[2]
for item in v.get('status',{}).get('traffic',[]) or []:
  if item.get('revisionName')==candidate and int(item.get('percent') or 0)>0:
    raise SystemExit('candidate unexpectedly receives traffic')
print('Candidate traffic verified at 0%.')
PY
printf 'WORKER_CANDIDATE_READY=%s\nWORKER_CANDIDATE_SOURCE_SHA=%s\nWORKER_CANDIDATE_EGRESS_MODE=%s\n' "$CANDIDATE" "$SOURCE_SHA" "$EGRESS_MODE"
