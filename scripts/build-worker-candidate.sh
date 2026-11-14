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
# Every later step, including the staged source tag, runs here with these
# exact tools. Refuse before any cloud call rather than after a deployment.
for tool in python3 gcloud git; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Refusing: required tool $tool is not on PATH." >&2; exit 2; }
done
python3 -c 'import hashlib, json, re, subprocess' || { echo "Refusing: python3 lacks the standard modules this build needs." >&2; exit 2; }

STAGED_SCAN_MODE="${FIXLIST_STAGED_SCAN_MODE:-off}"
STAGED_OWNER_IDS=""
case "$STAGED_SCAN_MODE" in
  off|inactive) ;;
  owner-canary)
    # One exact owner, bound to the source and cohort by a separate
    # confirmation. Base44 V9, the gateway and this worker must name the same
    # owner. Stage queue activation stays a separate, barrier-gated operation.
    STAGED_OWNER_IDS="${SCAN_STAGED_OWNER_IDS:-}"
    if [[ -n "${SCAN_PIPELINE_OWNER_IDS:-}" || -n "${SCAN_PIPELINE_MODE:-}" ]]; then
      echo "Refusing: owner-canary takes only SCAN_STAGED_OWNER_IDS; legacy aliases and mode overrides are refused." >&2
      exit 2
    fi
    ;;
  *) echo "Refusing unsupported FIXLIST_STAGED_SCAN_MODE=$STAGED_SCAN_MODE." >&2; exit 2 ;;
esac
if [[ "$STAGED_SCAN_MODE" == inactive && ( -n "${SCAN_STAGED_OWNER_IDS:-}" || -n "${SCAN_PIPELINE_OWNER_IDS:-}" || "${SCAN_PIPELINE_MODE:-monolith}" != monolith ) ]]; then
  echo "Refusing: an inactive staged candidate must use monolith mode and an empty owner cohort." >&2
  exit 2
fi
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO_ROOT/scripts/lib/release-source-guard.sh"
fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$CONFIRM"
SOURCE_SHA="$FIXLIST_EXACT_SOURCE_SHA"
if [[ "$STAGED_SCAN_MODE" == owner-canary ]]; then
  COHORT_SHA256="$(python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import staged_candidate_cloudbuild as c
try:
    print(c.cohort_sha256(c.owner_cohort(sys.argv[2])))
except ValueError as exc:
    raise SystemExit(f"Refusing: {exc}")' "$REPO_ROOT/scripts" "$STAGED_OWNER_IDS")"
  [[ "${STAGED_COHORT_CONFIRM:-}" == "STAGE-WORKER-OWNER-CANARY:${SOURCE_SHA}:${COHORT_SHA256}" ]] || {
    echo "Refusing: exact STAGE-WORKER-OWNER-CANARY:<source-sha>:<sorted-cohort-sha256> confirmation required." >&2
    exit 2
  }
fi

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
STAGED_CONFIG_JSON="$(mktemp)"
BUILD_RECORD_JSON="$(mktemp)"
BUILD_CONTEXT="$(mktemp -d)"
cleanup() {
  rm -f "$WORKER_JSON" "$REVISIONS_JSON" "$SERVICE_JSON" "$STAGED_CONFIG_JSON" "$BUILD_RECORD_JSON"
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

STAGED_TAG=""; STAGED_CONFIG_SHA256=""; STAGED_ENV_SUFFIX=""
if [[ "$STAGED_SCAN_MODE" == inactive || "$STAGED_SCAN_MODE" == owner-canary ]]; then
  python3 "$REPO_ROOT/scripts/staged_candidate_cloudbuild.py" prepare \
    --mode="$STAGED_SCAN_MODE" --owners="$STAGED_OWNER_IDS" \
    --worker-json="$WORKER_JSON" --source-sha="$SOURCE_SHA" --project="$PROJECT" --region="$REGION" \
    --bucket="${SCAN_WORKSPACE_BUCKET:-}" --queue-path="${SCAN_STAGE_TASKS_QUEUE_PATH:-}" > "$STAGED_CONFIG_JSON"
  readarray -t STAGED_VALUES < <(python3 - "$STAGED_CONFIG_JSON" <<'PY'
import json, sys
value = json.load(open(sys.argv[1])); print(value['tag']); print(value['digest'])
print(',' + ','.join(key + '=' + value['environment'][key] for key in sorted(value['environment'])))
PY
  )
  STAGED_TAG="${STAGED_VALUES[0]}"; STAGED_CONFIG_SHA256="${STAGED_VALUES[1]}"; STAGED_ENV_SUFFIX="${STAGED_VALUES[2]}"
fi

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
# is provenance metadata consumed by the selected immutable worker build config
# and is not copied into the worker image.
git -C "$REPO_ROOT" archive --format=tar "$SOURCE_SHA" | tar -xf - -C "$BUILD_CONTEXT"
printf '%s\n' "$SOURCE_SHA" > "$BUILD_CONTEXT/.fixlist-source-sha"

common_substitutions="_RELEASE_SHA=$SOURCE_SHA,_WORKER_SERVICE=$WORKER,_REGION=$REGION,_IMAGE=$IMAGE,_RUNTIME_SA=$RUNTIME_SA,_INVOKER_SA=$INVOKER_SA,_BASE44_APP_ID=$BASE44_APP,_BASE44_API_URL=$BASE44_API,_SIGNING_KEY_SECRET=$SIGNING_SECRET,_SIGNING_KEY_VERSION=$SIGNING_VERSION"
case "$EGRESS_MODE" in
  none)
    BUILD_CONFIG="$BUILD_CONTEXT/cloudbuild.durable-worker.yaml"
    BUILD_SUBSTITUTIONS="$common_substitutions"
    ;;
  static-canary)
    BUILD_CONFIG="$BUILD_CONTEXT/cloudbuild.durable-worker-static-egress-canary.yaml"
    BUILD_SUBSTITUTIONS="$common_substitutions,_EGRESS_NETWORK=$EGRESS_NETWORK,_EGRESS_SUBNET=$EGRESS_SUBNET"
    ;;
  *)
    echo "Refusing unsupported worker build egress mode." >&2
    exit 2
    ;;
esac
test -f "$BUILD_CONFIG" || { echo "Worker build config missing: $BUILD_CONFIG" >&2; exit 2; }
if [[ "$STAGED_SCAN_MODE" == inactive || "$STAGED_SCAN_MODE" == owner-canary ]]; then
  # The suffix contains environment commas. A separate substitutions delimiter
  # preserves those commas and the intentionally empty owner list verbatim.
  BUILD_SUBSTITUTIONS="^|^${BUILD_SUBSTITUTIONS//,/|}|_STAGED_SCAN_MODE=$STAGED_SCAN_MODE|_STAGED_ENV_SUFFIX=$STAGED_ENV_SUFFIX|_STAGED_TAG=$STAGED_TAG|_STAGED_CONFIG_SHA256=$STAGED_CONFIG_SHA256"
fi

gcloud builds submit "$BUILD_CONTEXT" \
  --project="$PROJECT" \
  --region="$REGION" \
  --config="$BUILD_CONFIG" \
  --service-account="$BUILD_SA_RESOURCE" \
  --substitutions="$BUILD_SUBSTITUTIONS" \
  --suppress-logs --format=json > "$BUILD_RECORD_JSON"

# The final build record names the exact image digest this build pushed and
# deployed. Bind the candidate to it before any tag is created.
readarray -t BUILD_VALUES < <(python3 - "$BUILD_RECORD_JSON" "$IMAGE:$SOURCE_SHA" <<'PY'
import json, re, sys
record = json.load(open(sys.argv[1])); expected = sys.argv[2]
if record.get('status') != 'SUCCESS' or not re.fullmatch(r'[0-9a-f-]{8,64}', str(record.get('id') or '')):
    raise SystemExit('Refusing: the build record is not an exact successful build.')
images = [item for item in (record.get('results') or {}).get('images') or [] if item.get('name') == expected]
digests = {str(item.get('digest') or '') for item in images}
if len(digests) != 1 or not re.fullmatch(r'sha256:[0-9a-f]{64}', next(iter(digests))):
    raise SystemExit('Refusing: the build record has no single exact digest for ' + expected + '.')
print(record['id']); print(next(iter(digests)))
PY
)
BUILD_ID="${BUILD_VALUES[0]:-}"; IMAGE_DIGEST="${BUILD_VALUES[1]:-}"
[[ -n "$BUILD_ID" && -n "$IMAGE_DIGEST" ]] || { echo "Refusing: build image digest unavailable." >&2; exit 2; }
printf 'build_id=%s\nimage_digest=%s\n' "$BUILD_ID" "$IMAGE_DIGEST"

gcloud run revisions list --service="$WORKER" --project="$PROJECT" --region="$REGION" --format=json > "$REVISIONS_JSON"
CANDIDATE="$(python3 - "$REVISIONS_JSON" "$SOURCE_SHA" "$EGRESS_MODE" "$EGRESS_NETWORK" "$EGRESS_SUBNET" "$STAGED_SCAN_MODE" "$STAGED_CONFIG_SHA256" "$IMAGE@$IMAGE_DIGEST" <<'PY'
import json, sys
rows=json.load(open(sys.argv[1])); sha, mode, network, subnet, staged, digest, image_ref = sys.argv[2:]
matches=[]
for r in rows:
  if (r.get('status') or {}).get('imageDigest') != image_ref:
    continue
  spec=r.get('spec',{}); c=(spec.get('containers') or [{}])[0]
  env={i.get('name'):i.get('value','') for i in c.get('env',[])}
  if env.get('FIXLIST_WORKER_SOURCE_SHA') != sha or env.get('FIXLIST_EGRESS_MODE','none') != mode:
    continue
  if staged in ('inactive', 'owner-canary') and env.get('FIXLIST_STAGED_CONFIG_SHA256') != digest:
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
if len(matches) != 1:
  raise SystemExit('Refusing: expected exactly one revision of this source running the built image digest, found %d.' % len(matches))
print(matches[0][1])
PY
)"
[[ -n "$CANDIDATE" ]] || { echo "No worker revision carries FIXLIST_WORKER_SOURCE_SHA=$SOURCE_SHA with the built image digest" >&2; exit 2; }

gcloud run revisions describe "$CANDIDATE" --project="$PROJECT" --region="$REGION" --format=json > "$REVISIONS_JSON"
python3 - "$REVISIONS_JSON" "$SOURCE_SHA" "$EGRESS_MODE" "$EGRESS_NETWORK" "$EGRESS_SUBNET" "$IMAGE@$IMAGE_DIGEST" <<'PY'
import json, sys
v=json.load(open(sys.argv[1])); sha, mode, network, subnet, image_ref = sys.argv[2:]
if (v.get('status') or {}).get('imageDigest') != image_ref: raise SystemExit('candidate does not run the image digest this build produced')
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

if [[ "$STAGED_SCAN_MODE" == inactive || "$STAGED_SCAN_MODE" == owner-canary ]]; then
  # Everything that can refuse the candidate runs BEFORE the immutable tag
  # exists: a tag created on a drifted revision could never be rebound.
  python3 - "$REVISIONS_JSON" "$STAGED_CONFIG_JSON" "$SOURCE_SHA" <<'PY'
import json, sys
revision = json.load(open(sys.argv[1])); config = json.load(open(sys.argv[2])); sha = sys.argv[3]
env = {item.get('name'): item.get('value', '') for item in (revision.get('spec', {}).get('containers') or [{}])[0].get('env', [])}
if env.get('FIXLIST_WORKER_SOURCE_SHA') != sha or any(env.get(key) != value for key, value in config['environment'].items()):
    raise SystemExit('Refusing: staged candidate environment does not match its exact source-bound configuration.')
if env.get('SCAN_PIPELINE_OWNER_IDS'):
    raise SystemExit('Refusing: staged candidate carries the legacy SCAN_PIPELINE_OWNER_IDS alias.')
PY
  # Create the immutable source tag here, not in a Cloud Build step: the
  # unpinned SDK image stopped shipping python3. Only the exact Ready revision
  # running this build's image digest may be tagged; the helper re-checks that,
  # refuses to rebind an existing tag and verifies the serving split unchanged.
  python3 "$REPO_ROOT/scripts/staged_candidate_cloudbuild.py" tag \
    --mode="$STAGED_SCAN_MODE" --source-sha="$SOURCE_SHA" --tag="$STAGED_TAG" \
    --digest="$STAGED_CONFIG_SHA256" --owners="$STAGED_OWNER_IDS" \
    --revision="$CANDIDATE" --image-ref="$IMAGE@$IMAGE_DIGEST" \
    --worker-service="$WORKER" --region="$REGION" --project="$PROJECT"
fi

gcloud run services describe "$WORKER" --project="$PROJECT" --region="$REGION" --format=json > "$SERVICE_JSON"
python3 - "$SERVICE_JSON" "$CANDIDATE" "$STAGED_SCAN_MODE" "$STAGED_CONFIG_JSON" "$REVISIONS_JSON" "$SOURCE_SHA" <<'PY'
import json,sys
v=json.load(open(sys.argv[1])); candidate, staged, config_path, revision_path, sha = sys.argv[2:]
for item in v.get('status',{}).get('traffic',[]) or []:
  if item.get('revisionName')==candidate and int(item.get('percent') or 0)>0:
    raise SystemExit('candidate unexpectedly receives traffic')
if staged in ('inactive', 'owner-canary'):
  config=json.load(open(config_path)); revision=json.load(open(revision_path))
  env={item.get('name'):item.get('value','') for item in (revision.get('spec',{}).get('containers') or [{}])[0].get('env',[])}
  if env.get('FIXLIST_WORKER_SOURCE_SHA') != sha or any(env.get(key) != value for key,value in config['environment'].items()):
    raise SystemExit('Refusing: staged candidate environment does not match its exact source-bound configuration.')
  if env.get('SCAN_PIPELINE_OWNER_IDS'):
    raise SystemExit('Refusing: staged candidate carries the legacy SCAN_PIPELINE_OWNER_IDS alias.')
  tags=[item for item in v.get('status',{}).get('traffic',[]) if item.get('tag') == config['tag']]
  if len(tags) != 1 or tags[0].get('revisionName') != candidate or tags[0].get('url','').rstrip('/') != config['environment']['SCAN_STAGE_TARGET_URL']:
    raise SystemExit('Refusing: immutable staged tag does not resolve to the exact configured candidate.')
print('Candidate traffic verified at 0%.')
PY
printf 'WORKER_CANDIDATE_READY=%s\nWORKER_CANDIDATE_SOURCE_SHA=%s\nWORKER_CANDIDATE_EGRESS_MODE=%s\n' "$CANDIDATE" "$SOURCE_SHA" "$EGRESS_MODE"
printf 'WORKER_CANDIDATE_BUILD_ID=%s\nWORKER_CANDIDATE_IMAGE_DIGEST=%s\n' "$BUILD_ID" "$IMAGE_DIGEST"
printf 'WORKER_CANDIDATE_STAGE_MODE=%s\n' "$STAGED_SCAN_MODE"
if [[ "$STAGED_SCAN_MODE" == inactive ]]; then printf 'WORKER_CANDIDATE_STAGE_TAG=%s\n' "$STAGED_TAG"; fi
