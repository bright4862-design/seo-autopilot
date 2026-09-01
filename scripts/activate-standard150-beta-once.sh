#!/usr/bin/env bash
set -euo pipefail

# One-shot owner-run activation helper for the exact merged Standard 150 beta.
# This helper lives on an ops-only branch so it cannot move the release source
# SHA. Execute it while the working tree itself is clean main at the exact SHA.
#
# Sequence:
#   1. Discover deployment inputs from the live worker; invent nothing.
#   2. Build/deploy the exact release as a private 0%-traffic candidate.
#   3. Verify the candidate configuration read-only.
#   4. Synchronize Base44's signing root, then deploy ONLY the durable JS/TS
#      functions and the site from the exact GitHub checkout. No Python is ever
#      deployed into Base44.
#   5. Pause an empty Standard 150 queue, promote the exact candidate, prove the
#      canonical worker is private/reachable, then resume the queue.
#
# Any failure after this script pauses the queue triggers automatic queue resume.
# Any failure after candidate promotion also attempts exact-revision rollback.
# It never deletes tasks, changes billing, enables Grok/Premium, or starts a scan.

EXPECTED_RELEASE_SHA="499d6479225d980ee95d60ef9df4118d726823d5"
EXPECTED_FINGERPRINT="5caec7fdcabceee7"
PROJECT="seo-autopilot-501517"
REGION="europe-west1"
WORKER="fixlist-standard150-worker"
QUEUE="fixlist-standard150"
INVOKER_SA="fixlist-standard150-invoker@${PROJECT}.iam.gserviceaccount.com"
BASE44_APP_ID="6a498732ec779dfaaeab0e53"
BASE44_API_URL="https://base44.app"
BASE44_CLI_VERSION="0.1.9"
BASE44_CLI_SRI="sha512-o1IFePlQHvUARUVr19FiYEakkPrwDf6IVcz3pWSngSaG+sBSs8t7T7coJir1N4yBFQ76052hjgqT2V+xC8BNOQ=="

say() { printf '\n========== %s ==========\n' "$*"; }
fail() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

for cmd in git gcloud python3 curl bash npm openssl; do
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
echo "beta_fingerprint=$EXPECTED_FINGERPRINT"

gcloud config set project "$PROJECT" >/dev/null
ACTIVE_ACCOUNT="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' | head -n1)"
[[ -n "$ACTIVE_ACCOUNT" ]] || fail "no active gcloud account"
echo "gcloud_account=$ACTIVE_ACCOUNT"

PREP_TMP="$(mktemp -d)"
DEPLOY_TMP=""
QUEUE_PAUSED_BY_US=0
PROMOTED=0
ACTIVATION_COMPLETE=0
OLD_REVISION=""
CANDIDATE_REVISION=""

recover_on_exit() {
  rc=$?
  trap - EXIT
  if [[ "$rc" -ne 0 && "$PROMOTED" -eq 1 && -n "$OLD_REVISION" ]]; then
    echo >&2
    echo "Activation failed after promotion; attempting rollback to $OLD_REVISION ..." >&2
    gcloud run services update-traffic "$WORKER" \
      --project="$PROJECT" --region="$REGION" \
      --to-revisions="${OLD_REVISION}=100" --quiet >/dev/null 2>&1 || \
      echo "WARNING: automatic traffic rollback failed; inspect Cloud Run immediately." >&2
  fi
  if [[ "$QUEUE_PAUSED_BY_US" -eq 1 ]]; then
    echo "Restoring Standard 150 queue to RUNNING ..." >&2
    gcloud tasks queues resume "$QUEUE" \
      --project="$PROJECT" --location="$REGION" --quiet >/dev/null 2>&1 || \
      echo "WARNING: automatic queue resume failed; inspect Cloud Tasks immediately." >&2
  fi
  rm -rf "$PREP_TMP"
  [[ -n "$DEPLOY_TMP" ]] && rm -rf "$DEPLOY_TMP"
  exit "$rc"
}
trap recover_on_exit EXIT
chmod 700 "$PREP_TMP"

say "1/7 DISCOVER LIVE DEPLOYMENT INPUTS"
gcloud run services describe "$WORKER" \
  --project="$PROJECT" --region="$REGION" --format=json > "$PREP_TMP/before.json"

python3 - "$PREP_TMP/before.json" "$PREP_TMP/inputs.env" <<'PY'
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
old = ""
for t in status.get("traffic") or []:
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
# Identifiers/paths only; no secret payload is read in discovery.
# shellcheck disable=SC1090
source "$PREP_TMP/inputs.env"
printf 'image_base=%s\nruntime_sa=%s\nsigning_secret_ref=%s:%s\nrollback_revision=%s\n' \
  "$IMAGE_BASE" "$RUNTIME_SA" "$SIGNING_SECRET" "$SIGNING_VERSION" "$OLD_REVISION"

QUEUE_STATE_START="$(gcloud tasks queues describe "$QUEUE" \
  --project="$PROJECT" --location="$REGION" --format='value(state)')"
[[ "$QUEUE_STATE_START" == "RUNNING" ]] \
  || fail "Standard 150 queue must start RUNNING; got $QUEUE_STATE_START"
START_TASKS="$(gcloud tasks list --project="$PROJECT" --location="$REGION" \
  --queue="$QUEUE" --format='value(name)' 2>/dev/null || true)"
[[ -z "$START_TASKS" ]] || fail "queue already contains tasks; refusing candidate activation"
echo "queue_preflight=RUNNING_AND_EMPTY"

say "2/7 BUILD + DEPLOY EXACT SHA AT 0% TRAFFIC"
gcloud builds submit . \
  --project="$PROJECT" \
  --config=cloudbuild.durable-worker.yaml \
  --substitutions="_RELEASE_SHA=${EXPECTED_RELEASE_SHA},_WORKER_SERVICE=${WORKER},_REGION=${REGION},_IMAGE=${IMAGE_BASE},_RUNTIME_SA=${RUNTIME_SA},_INVOKER_SA=${INVOKER_SA},_BASE44_APP_ID=${BASE44_APP_ID},_BASE44_API_URL=${BASE44_API_URL},_SIGNING_KEY_SECRET=${SIGNING_SECRET},_SIGNING_KEY_VERSION=${SIGNING_VERSION}"

gcloud run services describe "$WORKER" \
  --project="$PROJECT" --region="$REGION" --format=json > "$PREP_TMP/candidate.json"
CANDIDATE_REVISION="$(python3 - "$PREP_TMP/candidate.json" "$OLD_REVISION" <<'PY'
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
printf 'candidate_revision=%s\ncandidate_image=%s\ncandidate_traffic=0%%\n' \
  "$CANDIDATE_REVISION" "$CANDIDATE_IMAGE"

say "3/7 VERIFY CANDIDATE BEFORE TRAFFIC"
# post_deploy_verify.sh inspects the service template, where Cloud Run preserves
# the release tag supplied at deploy time. Compare tag-to-tag there; then verify
# the exact candidate revision independently below using its resolved digest.
WORKER_SERVICE="$WORKER" \
REGION="$REGION" \
PROJECT="$PROJECT" \
EXPECTED_IMAGE="${IMAGE_BASE}:${EXPECTED_RELEASE_SHA}" \
EXPECTED_RUNTIME_SA="$RUNTIME_SA" \
EXPECTED_INVOKER_SA="$INVOKER_SA" \
BASE44_APP_ID="$BASE44_APP_ID" \
EXPECTED_SIGNING_SECRET="$SIGNING_SECRET" \
EXPECTED_SIGNING_VERSION="$SIGNING_VERSION" \
  bash scripts/post_deploy_verify.sh

# The service-level verifier may still report the previously serving
# latestReadyRevisionName while a new --no-traffic revision is ready. Verify the
# exact candidate by revision name so the old ready revision cannot satisfy this
# gate. gcloud revision describe resolves the container image to an immutable
# digest, which must match the digest captured immediately after deployment.
gcloud run revisions describe "$CANDIDATE_REVISION" \
  --project="$PROJECT" --region="$REGION" --format=json > "$PREP_TMP/candidate-revision.json"
python3 - "$PREP_TMP/candidate-revision.json" "$CANDIDATE_REVISION" "$CANDIDATE_IMAGE" \
  "$RUNTIME_SA" "$SIGNING_SECRET" "$SIGNING_VERSION" <<'PY'
import json, sys
path, expected_revision, expected_image, expected_sa, expected_secret, expected_version = sys.argv[1:7]
d = json.load(open(path, encoding="utf-8"))
name = str((d.get("metadata") or {}).get("name") or "").strip()
if name != expected_revision:
    raise SystemExit(f"candidate revision identity mismatch: got {name!r}, expected {expected_revision!r}")
status = d.get("status") or {}
ready = any(
    str(c.get("type") or "") == "Ready" and str(c.get("status") or "").lower() == "true"
    for c in status.get("conditions") or []
)
if not ready:
    raise SystemExit("exact candidate revision is not Ready")
spec = d.get("spec") or {}
containers = spec.get("containers") or []
if not containers:
    raise SystemExit("exact candidate revision has no container")
c = containers[0]
image = str(c.get("image") or "").strip()
if image != expected_image:
    raise SystemExit(f"candidate digest mismatch: got {image!r}, expected {expected_image!r}")
if "@sha256:" not in image:
    raise SystemExit(f"candidate image is not resolved to an immutable digest: {image!r}")
sa = str(spec.get("serviceAccountName") or "").strip()
if sa != expected_sa:
    raise SystemExit(f"candidate runtime service account mismatch: got {sa!r}, expected {expected_sa!r}")
if str(spec.get("timeoutSeconds") or "") != "480":
    raise SystemExit(f"candidate timeout is {spec.get('timeoutSeconds')!r}, expected 480")
if str(spec.get("containerConcurrency") or "") != "1":
    raise SystemExit(f"candidate concurrency is {spec.get('containerConcurrency')!r}, expected 1")
env = c.get("env") or []
secret_env = next((e for e in env if e.get("name") == "SCAN_EVIDENCE_SIGNING_KEY"), None)
if secret_env is None:
    raise SystemExit("candidate signing-key environment reference is absent")
ref = (secret_env.get("valueFrom") or {}).get("secretKeyRef") or {}
if str(ref.get("name") or "") != expected_secret or str(ref.get("key") or "") != expected_version:
    raise SystemExit(
        "candidate signing-key reference mismatch: "
        f"got {ref.get('name')!r}:{ref.get('key')!r}, expected {expected_secret!r}:{expected_version!r}"
    )
print(f"PASS — exact candidate revision {expected_revision} is Ready")
print(f"PASS — exact candidate resolved image matches immutable digest {expected_image}")
PY

say "4/7 SYNCHRONIZE SIGNING ROOT + GITHUB SOURCE INTO BASE44"
# This subprocess removes its plaintext secret temp files immediately on return.
# It also persists only the Base44 device-login credential in the user's normal
# CLI auth store, so the following deployment can reuse the authenticated session.
bash scripts/sync-base44-signing-key.sh

# Reinstall the same CLI from the same independently pinned/verified artifact,
# now only to deploy source. No signing-key plaintext is present at this stage.
DEPLOY_TMP="$(mktemp -d)"
chmod 700 "$DEPLOY_TMP"
npm pack "base44@${BASE44_CLI_VERSION}" --pack-destination "$DEPLOY_TMP" >/dev/null
BASE44_TGZ="$DEPLOY_TMP/base44-${BASE44_CLI_VERSION}.tgz"
[[ -s "$BASE44_TGZ" ]] || fail "verified Base44 CLI tarball was not downloaded"
GOT_SRI="sha512-$(openssl dgst -sha512 -binary "$BASE44_TGZ" | openssl base64 -A)"
[[ "$GOT_SRI" == "$BASE44_CLI_SRI" ]] \
  || fail "Base44 CLI integrity mismatch during source deployment"
npm install --prefix "$DEPLOY_TMP/cli" --no-save --save-exact --ignore-scripts "$BASE44_TGZ" >/dev/null
BASE44_CLI="$DEPLOY_TMP/cli/node_modules/.bin/base44"
[[ -x "$BASE44_CLI" ]] || fail "verified Base44 CLI executable missing"

"$BASE44_CLI" --app-id "$BASE44_APP_ID" functions deploy \
  startStandardScanJob durableScanWorkerControl persistDurableScanAuthority
"$BASE44_CLI" --app-id "$BASE44_APP_ID" deploy --site-only

echo "Base44 durable functions + site deployed from release_sha=$EXPECTED_RELEASE_SHA"
rm -rf "$DEPLOY_TMP"
DEPLOY_TMP=""

say "5/7 QUIESCE EMPTY QUEUE"
# Re-check after the build/login/deploy window. We never delete or adopt an
# unexpected task; a non-empty queue requires explicit disposition instead.
TASKS_BEFORE_PROMOTION="$(gcloud tasks list --project="$PROJECT" --location="$REGION" \
  --queue="$QUEUE" --format='value(name)' 2>/dev/null || true)"
[[ -z "$TASKS_BEFORE_PROMOTION" ]] || fail "queue gained tasks; refusing traffic promotion"
gcloud tasks queues pause "$QUEUE" --project="$PROJECT" --location="$REGION" --quiet
QUEUE_PAUSED_BY_US=1

TASKS_AFTER_PAUSE="$(gcloud tasks list --project="$PROJECT" --location="$REGION" \
  --queue="$QUEUE" --format='value(name)' 2>/dev/null || true)"
[[ -z "$TASKS_AFTER_PAUSE" ]] || fail "queue contains tasks after pause; refusing traffic promotion"

echo "queue=PAUSED_AND_EMPTY"

say "6/7 PROMOTE EXACT CANDIDATE WITH AUTOMATIC ROLLBACK"
gcloud run services update-traffic "$WORKER" \
  --project="$PROJECT" --region="$REGION" \
  --to-revisions="${CANDIDATE_REVISION}=100" --quiet
PROMOTED=1

WORKER_URL="$(gcloud run services describe "$WORKER" \
  --project="$PROJECT" --region="$REGION" --format='value(status.url)')"
HTTP_FILE="$PREP_TMP/http_code"
if curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "$WORKER_URL/scan-job" > "$HTTP_FILE"; then
  CODE="$(cat "$HTTP_FILE")"
else
  CODE="000"
fi
case "$CODE" in
  401|403) echo "PASS — canonical worker is serving and private ($CODE)" ;;
  *) fail "candidate serving probe returned $CODE; automatic rollback will run" ;;
esac

gcloud run services describe "$WORKER" \
  --project="$PROJECT" --region="$REGION" --format=json > "$PREP_TMP/promoted.json"
python3 - "$PREP_TMP/promoted.json" "$CANDIDATE_REVISION" <<'PY'
import json, sys
d=json.load(open(sys.argv[1], encoding="utf-8")); expected=sys.argv[2]
positive=[]
for t in (d.get("status") or {}).get("traffic") or []:
    try: pct=int(t.get("percent") or 0)
    except Exception: pct=0
    if pct <= 0: continue
    name=str(t.get("revisionName") or t.get("revision") or "").strip()
    positive.append((name,pct))
if positive != [(expected,100)]:
    raise SystemExit(f"traffic is not exact candidate=100: {positive!r}")
print("PASS — exact candidate holds 100% traffic")
PY

gcloud tasks queues resume "$QUEUE" --project="$PROJECT" --location="$REGION" --quiet
QUEUE_PAUSED_BY_US=0

say "7/7 FINAL INFRA VERIFICATION"
FINAL_QUEUE_STATE="$(gcloud tasks queues describe "$QUEUE" \
  --project="$PROJECT" --location="$REGION" --format='value(state)')"
[[ "$FINAL_QUEUE_STATE" == "RUNNING" ]] || fail "queue did not return to RUNNING"
FINAL_TASKS="$(gcloud tasks list --project="$PROJECT" --location="$REGION" \
  --queue="$QUEUE" --format='value(name)' 2>/dev/null || true)"
[[ -z "$FINAL_TASKS" ]] || fail "unexpected task exists before customer acceptance"

ACTIVATION_COMPLETE=1
printf 'release_sha=%s\nfingerprint=%s\nworker_revision=%s\nworker_image=%s\ntraffic=100%%\nqueue_state=%s\nbase44_source_sha=%s\n' \
  "$EXPECTED_RELEASE_SHA" "$EXPECTED_FINGERPRINT" "$CANDIDATE_REVISION" \
  "$CANDIDATE_IMAGE" "$FINAL_QUEUE_STATE" "$EXPECTED_RELEASE_SHA"

echo
echo "BETA_INFRA_ACTIVATED"
echo "No customer scan was started. Fresh Funbooker acceptance is still required."