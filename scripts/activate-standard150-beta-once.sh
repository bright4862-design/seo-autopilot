#!/usr/bin/env bash
set -euo pipefail

# One-shot owner-run activation helper for the exact merged Standard 150 beta.
# This script lives on an ops-only branch so using it does not move the release
# source SHA. It must be executed while the working tree itself is clean main at
# EXPECTED_RELEASE_SHA.
#
# Sequence:
#   1. Discover all deployment inputs from the live worker; invent nothing.
#   2. Build/deploy EXPECTED_RELEASE_SHA as a private 0%-traffic candidate.
#   3. Verify the candidate configuration read-only.
#   4. Synchronize Base44's signing root from the worker's pinned GCP secret.
#      Base44 device login happens BEFORE the secret is read.
#   5. Pause the Standard 150 queue, require it to be empty, promote the exact
#      candidate, prove the canonical worker is still private/reachable, resume.
#
# It never deletes tasks, changes billing, enables Grok/Premium, or starts a scan.

EXPECTED_RELEASE_SHA="499d6479225d980ee95d60ef9df4118d726823d5"
PROJECT="seo-autopilot-501517"
REGION="europe-west1"
WORKER="fixlist-standard150-worker"
QUEUE="fixlist-standard150"
INVOKER_SA="fixlist-standard150-invoker@${PROJECT}.iam.gserviceaccount.com"
BASE44_APP_ID="6a498732ec779dfaaeab0e53"
BASE44_API_URL="https://base44.app"

say() { printf '\n========== %s ==========\n' "$*"; }
fail() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

for cmd in git gcloud python3 curl bash; do
  command -v "$cmd" >/dev/null 2>&1 || fail "$cmd is required"
done

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[[ -n "$REPO_ROOT" ]] || fail "run this from the seo-autopilot repository"
cd "$REPO_ROOT"

git fetch origin main --quiet
LOCAL_SHA="$(git rev-parse HEAD)"
REMOTE_SHA="$(git rev-parse origin/main)"
[[ "$LOCAL_SHA" == "$EXPECTED_RELEASE_SHA" ]] \
  || fail "checkout is $LOCAL_SHA; expected exact release $EXPECTED_RELEASE_SHA"
[[ "$REMOTE_SHA" == "$EXPECTED_RELEASE_SHA" ]] \
  || fail "origin/main moved to $REMOTE_SHA; refusing to deploy a stale release"
[[ -z "$(git status --porcelain --untracked-files=all)" ]] \
  || fail "working tree is not clean"

echo "release_sha=$EXPECTED_RELEASE_SHA"

gcloud config set project "$PROJECT" >/dev/null
ACTIVE_ACCOUNT="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' | head -n1)"
[[ -n "$ACTIVE_ACCOUNT" ]] || fail "no active gcloud account"
echo "gcloud_account=$ACTIVE_ACCOUNT"

TMP="$(mktemp -d)"
QUEUE_WAS_PAUSED=0
PROMOTED=0
OLD_REVISION=""
CANDIDATE_REVISION=""
cleanup() {
  rm -rf "$TMP"
}
trap cleanup EXIT
chmod 700 "$TMP"

say "1/6 DISCOVER LIVE DEPLOYMENT INPUTS"
gcloud run services describe "$WORKER" \
  --project="$PROJECT" --region="$REGION" --format=json > "$TMP/before.json"

python3 - "$TMP/before.json" "$TMP/inputs.env" <<'PY'
import json, re, sys
src, out = sys.argv[1:3]
d = json.load(open(src, encoding="utf-8"))
spec = d.get("spec", {}).get("template", {}).get("spec", {})
containers = spec.get("containers") or []
if not containers:
    raise SystemExit("live worker has no container")
c = containers[0]
image = str(c.get("image") or "").strip()
runtime = str(spec.get("serviceAccountName") or "").strip()
if not image or not runtime:
    raise SystemExit("live worker image/runtime identity missing")
# Cloud Run may expose a resolved digest. Cloud Build needs the repository/image
# path without tag or digest.
image_base = image.split("@", 1)[0]
last = image_base.rsplit("/", 1)[-1]
if ":" in last:
    image_base = image_base.rsplit(":", 1)[0]
if ".pkg.dev/" not in image_base:
    raise SystemExit(f"refusing non-Artifact-Registry image path: {image_base}")
secret_name = secret_version = ""
for env in c.get("env") or []:
    if env.get("name") != "SCAN_EVIDENCE_SIGNING_KEY":
        continue
    ref = (env.get("valueFrom") or {}).get("secretKeyRef") or {}
    secret_name = str(ref.get("name") or "").strip()
    secret_version = str(ref.get("key") or "").strip()
    break
if not secret_name or not secret_version.isdigit():
    raise SystemExit("live worker signing secret is not pinned to a numeric version")
status = d.get("status") or {}
latest_ready = str(status.get("latestReadyRevisionName") or "").strip()
traffic = status.get("traffic") or []
old = ""
for t in traffic:
    try:
        pct = int(t.get("percent") or 0)
    except Exception:
        pct = 0
    if pct != 100:
        continue
    old = str(t.get("revisionName") or t.get("revision") or "").strip()
    if not old and t.get("latestRevision"):
        old = latest_ready
    if old:
        break
if not old:
    raise SystemExit("could not identify the exact 100%-traffic rollback revision")
with open(out, "w", encoding="utf-8") as fh:
    for k, v in {
        "IMAGE_BASE": image_base,
        "RUNTIME_SA": runtime,
        "SIGNING_SECRET": secret_name,
        "SIGNING_VERSION": secret_version,
        "OLD_REVISION": old,
    }.items():
        if not re.fullmatch(r"[A-Za-z0-9_./:@+-]+", v):
            raise SystemExit(f"unexpected characters in discovered {k}")
        fh.write(f"{k}={v}\n")
PY
# Values are identifiers/paths only; no secret payload is read here.
# shellcheck disable=SC1090
source "$TMP/inputs.env"
OLD_REVISION="$OLD_REVISION"
printf 'image_base=%s\nruntime_sa=%s\nsigning_secret_ref=%s:%s\nrollback_revision=%s\n' \
  "$IMAGE_BASE" "$RUNTIME_SA" "$SIGNING_SECRET" "$SIGNING_VERSION" "$OLD_REVISION"

say "2/6 BUILD + DEPLOY EXACT SHA AT 0% TRAFFIC"
gcloud builds submit . \
  --project="$PROJECT" \
  --config=cloudbuild.durable-worker.yaml \
  --substitutions="_RELEASE_SHA=${EXPECTED_RELEASE_SHA},_WORKER_SERVICE=${WORKER},_REGION=${REGION},_IMAGE=${IMAGE_BASE},_RUNTIME_SA=${RUNTIME_SA},_INVOKER_SA=${INVOKER_SA},_BASE44_APP_ID=${BASE44_APP_ID},_BASE44_API_URL=${BASE44_API_URL},_SIGNING_KEY_SECRET=${SIGNING_SECRET},_SIGNING_KEY_VERSION=${SIGNING_VERSION}"

gcloud run services describe "$WORKER" \
  --project="$PROJECT" --region="$REGION" --format=json > "$TMP/candidate.json"
CANDIDATE_REVISION="$(python3 - "$TMP/candidate.json" "$OLD_REVISION" <<'PY'
import json, sys
d=json.load(open(sys.argv[1], encoding="utf-8")); old=sys.argv[2]
rev=str((d.get("status") or {}).get("latestCreatedRevisionName") or "").strip()
if not rev or rev == old:
    raise SystemExit("Cloud Build did not create a distinct candidate revision")
for t in (d.get("status") or {}).get("traffic") or []:
    name=str(t.get("revisionName") or t.get("revision") or "").strip()
    if name == rev and int(t.get("percent") or 0) > 0:
        raise SystemExit(f"candidate unexpectedly has traffic: {t.get('percent')}%")
print(rev)
PY
)"
[[ -n "$CANDIDATE_REVISION" ]] || fail "candidate revision could not be resolved"
CANDIDATE_IMAGE="$(gcloud run revisions describe "$CANDIDATE_REVISION" \
  --project="$PROJECT" --region="$REGION" --format='value(spec.containers[0].image)')"
[[ -n "$CANDIDATE_IMAGE" ]] || fail "candidate image could not be resolved"
printf 'candidate_revision=%s\ncandidate_image=%s\n' "$CANDIDATE_REVISION" "$CANDIDATE_IMAGE"

say "3/6 VERIFY CANDIDATE BEFORE TRAFFIC"
WORKER_SERVICE="$WORKER" \
REGION="$REGION" \
PROJECT="$PROJECT" \
EXPECTED_IMAGE="$CANDIDATE_IMAGE" \
EXPECTED_RUNTIME_SA="$RUNTIME_SA" \
EXPECTED_INVOKER_SA="$INVOKER_SA" \
BASE44_APP_ID="$BASE44_APP_ID" \
EXPECTED_SIGNING_SECRET="$SIGNING_SECRET" \
EXPECTED_SIGNING_VERSION="$SIGNING_VERSION" \
  bash scripts/post_deploy_verify.sh

say "4/6 SYNCHRONIZE BASE44 SIGNING ROOT"
# Hardened script verifies the pinned Base44 CLI tarball, performs device login
# before it reads the secret, imports the exact live worker root, and removes its
# temporary files on exit.
bash scripts/sync-base44-signing-key.sh

say "5/6 QUIESCE QUEUE + PROMOTE EXACT CANDIDATE"
QUEUE_STATE="$(gcloud tasks queues describe "$QUEUE" \
  --project="$PROJECT" --location="$REGION" --format='value(state)')"
case "$QUEUE_STATE" in
  RUNNING)
    gcloud tasks queues pause "$QUEUE" --project="$PROJECT" --location="$REGION" --quiet
    QUEUE_WAS_PAUSED=1
    ;;
  PAUSED)
    echo "Queue was already PAUSED; preserving that intent until verification completes."
    ;;
  *) fail "unexpected queue state before activation: $QUEUE_STATE" ;;
esac

TASKS="$(gcloud tasks list --project="$PROJECT" --location="$REGION" --queue="$QUEUE" --format='value(name)' 2>/dev/null || true)"
if [[ -n "$TASKS" ]]; then
  if [[ "$QUEUE_WAS_PAUSED" -eq 1 ]]; then
    gcloud tasks queues resume "$QUEUE" --project="$PROJECT" --location="$REGION" --quiet || true
  fi
  echo "$TASKS" >&2
  fail "queue contains tasks; refusing traffic promotion without disposition"
fi

gcloud run services update-traffic "$WORKER" \
  --project="$PROJECT" --region="$REGION" \
  --to-revisions="${CANDIDATE_REVISION}=100" --quiet
PROMOTED=1

WORKER_URL="$(gcloud run services describe "$WORKER" \
  --project="$PROJECT" --region="$REGION" --format='value(status.url)')"
CODE="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "$WORKER_URL/scan-job" || printf '000')"
case "$CODE" in
  401|403) echo "PASS — canonical worker is serving and private ($CODE)" ;;
  *)
    echo "Promotion verification failed with HTTP $CODE; rolling back to $OLD_REVISION." >&2
    gcloud run services update-traffic "$WORKER" \
      --project="$PROJECT" --region="$REGION" \
      --to-revisions="${OLD_REVISION}=100" --quiet || true
    if [[ "$QUEUE_WAS_PAUSED" -eq 1 ]]; then
      gcloud tasks queues resume "$QUEUE" --project="$PROJECT" --location="$REGION" --quiet || true
    fi
    fail "candidate did not satisfy the private serving probe"
    ;;
esac

TRAFFIC_REV="$(gcloud run services describe "$WORKER" \
  --project="$PROJECT" --region="$REGION" \
  --format='value(status.traffic[0].revisionName)')"
TRAFFIC_PCT="$(gcloud run services describe "$WORKER" \
  --project="$PROJECT" --region="$REGION" \
  --format='value(status.traffic[0].percent)')"
[[ "$TRAFFIC_REV" == "$CANDIDATE_REVISION" && "$TRAFFIC_PCT" == "100" ]] || {
  gcloud run services update-traffic "$WORKER" \
    --project="$PROJECT" --region="$REGION" \
    --to-revisions="${OLD_REVISION}=100" --quiet || true
  if [[ "$QUEUE_WAS_PAUSED" -eq 1 ]]; then
    gcloud tasks queues resume "$QUEUE" --project="$PROJECT" --location="$REGION" --quiet || true
  fi
  fail "traffic did not settle at exact candidate 100%; rolled back"
}

if [[ "$QUEUE_WAS_PAUSED" -eq 1 ]]; then
  gcloud tasks queues resume "$QUEUE" --project="$PROJECT" --location="$REGION" --quiet
fi

say "6/6 FINAL INFRA VERIFICATION"
FINAL_QUEUE_STATE="$(gcloud tasks queues describe "$QUEUE" \
  --project="$PROJECT" --location="$REGION" --format='value(state)')"
printf 'release_sha=%s\nfingerprint=%s\nworker_revision=%s\nworker_image=%s\ntraffic=100%%\nqueue_state=%s\n' \
  "$EXPECTED_RELEASE_SHA" "5caec7fdcabceee7" "$CANDIDATE_REVISION" "$CANDIDATE_IMAGE" "$FINAL_QUEUE_STATE"

if [[ "$QUEUE_WAS_PAUSED" -eq 1 && "$FINAL_QUEUE_STATE" != "RUNNING" ]]; then
  fail "queue was originally running but did not return to RUNNING"
fi

echo
echo "BETA_INFRA_ACTIVATED"
echo "No customer scan was started. Fresh Funbooker acceptance is still required."
