#!/usr/bin/env bash
# Read-only post-deploy verification for the durable Standard 150 worker.
#
# STRICTLY READ-ONLY. Uses only `gcloud ... describe` / `list` and one
# unauthenticated probe that is EXPECTED to be rejected. It never:
#   - runs a customer scan or posts to /scan or /scan-job
#   - promotes, splits, or migrates traffic
#   - deploys, updates, or deletes any resource
#   - reads or prints a secret value
#
# Usage (every value explicit, nothing invented):
#   WORKER_SERVICE=... REGION=... PROJECT=... \
#   EXPECTED_IMAGE=... EXPECTED_RUNTIME_SA=... EXPECTED_INVOKER_SA=... \
#   EXPECTED_SIGNING_SECRET=... EXPECTED_SIGNING_VERSION=... \
#   TASKS_QUEUE=fixlist-standard150 DRAIN_QUEUE=fixlist-standard150-drain \
#   EXPECTED_SCAN_QUEUE_CONCURRENCY=1|3|5|10 \
#   BASE44_PULLED_FUNCTIONS_DIR=<fresh-read-only-cli-pull>/base44/functions \
#   BASE44_PULLED_ENTITIES_DIR=<fresh-read-only-cli-pull>/base44/entities \
#   [BASE44_APP_ID=...] [NODE_BIN=node] \
#   bash scripts/post_deploy_verify.sh
#
# All EXPECTED_* inputs above are REQUIRED. The deployed revision must use the
# exact image and runtime/invoker identities and mount SCAN_EVIDENCE_SIGNING_KEY
# from exactly that secret at exactly that numeric version. Metadata only -- the
# payload is never accessed.

set -uo pipefail

FAILED=0
pass() { printf "  PASS  %s\n" "$1"; }
fail() { printf "  FAIL  %s\n" "$1"; FAILED=$((FAILED + 1)); }
skip() { printf "  SKIP  %s\n" "$1"; }

: "${WORKER_SERVICE:=}"
: "${REGION:=}"
: "${PROJECT:=}"
: "${EXPECTED_IMAGE:=}"
: "${EXPECTED_RUNTIME_SA:=}"
: "${EXPECTED_INVOKER_SA:=}"
: "${BASE44_APP_ID:=}"
: "${EXPECTED_SIGNING_SECRET:=}"
: "${EXPECTED_SIGNING_VERSION:=}"
: "${TASKS_QUEUE:=}"
: "${DRAIN_QUEUE:=}"
: "${EXPECTED_SCAN_QUEUE_CONCURRENCY:=}"
: "${BASE44_PULLED_FUNCTIONS_DIR:=}"
: "${BASE44_PULLED_ENTITIES_DIR:=}"
: "${NODE_BIN:=node}"

if [ -z "$WORKER_SERVICE" ] || [ -z "$REGION" ] || [ -z "$PROJECT" ]; then
  echo "WORKER_SERVICE, REGION and PROJECT are required. Nothing is guessed."
  exit 2
fi
if [ -z "$EXPECTED_IMAGE" ] || [ -z "$EXPECTED_RUNTIME_SA" ] || [ -z "$EXPECTED_INVOKER_SA" ] || \
   [ -z "$EXPECTED_SIGNING_SECRET" ] || [ -z "$EXPECTED_SIGNING_VERSION" ] || \
   [ -z "$TASKS_QUEUE" ] || [ -z "$DRAIN_QUEUE" ] || [ -z "$EXPECTED_SCAN_QUEUE_CONCURRENCY" ] || \
   [ -z "$BASE44_PULLED_FUNCTIONS_DIR" ] || [ -z "$BASE44_PULLED_ENTITIES_DIR" ]; then
  echo "EXPECTED_IMAGE, EXPECTED_RUNTIME_SA, EXPECTED_INVOKER_SA, EXPECTED_SIGNING_SECRET and EXPECTED_SIGNING_VERSION are required."
  echo "TASKS_QUEUE, DRAIN_QUEUE and EXPECTED_SCAN_QUEUE_CONCURRENCY are required."
  echo "BASE44_PULLED_FUNCTIONS_DIR is required and must name a fresh authenticated CLI pull of deployed functions."
  echo "BASE44_PULLED_ENTITIES_DIR is required and must name the same pull's deployed entity schemas."
  echo "The verifier refuses an unpinned image or identity expectation."
  echo "The signing key must be pinned to an exact numeric version; 'latest' is prohibited."
  exit 2
fi
case "$EXPECTED_SIGNING_VERSION" in
  latest|LATEST) echo "EXPECTED_SIGNING_VERSION='latest' is prohibited; pin a numeric enabled version."; exit 2 ;;
  ''|*[!0-9]*)   echo "EXPECTED_SIGNING_VERSION='$EXPECTED_SIGNING_VERSION' is not numeric."; exit 2 ;;
esac
if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud not installed; cannot verify a deployed service."
  exit 2
fi

DESCRIBE=$(gcloud run services describe "$WORKER_SERVICE" \
  --region="$REGION" --project="$PROJECT" --format=json 2>/dev/null)
if [ -z "$DESCRIBE" ]; then
  echo "Could not describe service $WORKER_SERVICE in $REGION. Wrong name/region/permissions?"
  exit 2
fi

jqq() { printf "%s" "$DESCRIBE" | python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null; }

echo "=== 1. Worker privacy ==="
# IAM policy is authoritative: allUsers/allAuthenticatedUsers must not hold run.invoker.
if ! POLICY=$(gcloud run services get-iam-policy "$WORKER_SERVICE" \
  --region="$REGION" --project="$PROJECT" --format=json 2>/dev/null); then
  echo "Could not read the worker IAM policy; privacy and invoker identity are unverified."
  exit 2
fi
if [ -z "$POLICY" ]; then
  echo "Worker IAM policy was empty; privacy and invoker identity are unverified."
  exit 2
fi
IAM_RESULT=$(printf "%s" "$POLICY" | EXPECTED_INVOKER_SA="$EXPECTED_INVOKER_SA" python3 -c '
import json, os, sys
d = json.load(sys.stdin)
bindings = d.get("bindings")
if not isinstance(bindings, list):
    raise ValueError("bindings is not a list")
public = False
exact_invoker = False
expected = "serviceAccount:" + os.environ["EXPECTED_INVOKER_SA"]
for binding in bindings:
    if not isinstance(binding, dict):
        raise ValueError("binding is not an object")
    members = binding.get("members", [])
    if not isinstance(members, list):
        raise ValueError("members is not a list")
    if binding.get("role") == "roles/run.invoker":
        public = public or any(m in ("allUsers", "allAuthenticatedUsers") for m in members)
        exact_invoker = exact_invoker or expected in members
print(("PUBLIC" if public else "PRIVATE") + " " + ("INVOKER_OK" if exact_invoker else "INVOKER_MISSING"))
' 2>/dev/null) || {
  echo "Worker IAM policy was malformed; privacy and invoker identity are unverified."
  exit 2
}
case "$IAM_RESULT" in
  "PRIVATE INVOKER_OK")
    pass "no public principal holds roles/run.invoker"
    pass "exact invoker holds roles/run.invoker"
    ;;
  "PUBLIC "*) fail "service is PUBLIC (allUsers/allAuthenticatedUsers hold roles/run.invoker)" ;;
  "PRIVATE INVOKER_MISSING")
    fail "expected invoker serviceAccount:$EXPECTED_INVOKER_SA does not hold roles/run.invoker"
    ;;
  *) echo "Worker IAM policy result was indeterminate; failing closed."; exit 2 ;;
esac

# Corroborate with an unauthenticated probe that must be rejected. GET on a
# POST-only route: no job is created either way.
URL=$(jqq "d.get('status',{}).get('url','')")
if [ -n "$URL" ] && command -v curl >/dev/null 2>&1; then
  CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 "$URL/scan-job" 2>/dev/null || echo "000")
  case "$CODE" in
    401|403) pass "unauthenticated probe rejected ($CODE)" ;;
    000)     skip "probe could not reach the service" ;;
    *)       fail "unauthenticated probe returned $CODE; expected 401/403" ;;
  esac
else
  skip "no service URL or curl unavailable"
fi

echo
echo "=== 2. Revision and image identity ==="
REV=$(jqq "d.get('status',{}).get('latestReadyRevisionName','')")
IMG=$(jqq "d['spec']['template']['spec']['containers'][0].get('image','')")
[ -n "$REV" ] && pass "latest ready revision: $REV" || fail "no ready revision"
[ -n "$IMG" ] && pass "image: $IMG" || fail "no image recorded"
[ "$IMG" = "$EXPECTED_IMAGE" ] \
  && pass "image matches EXPECTED_IMAGE" \
  || fail "image mismatch: expected $EXPECTED_IMAGE"

echo
echo "=== 3. Runtime configuration ==="
SA=$(jqq "d['spec']['template']['spec'].get('serviceAccountName','')")
TO=$(jqq "d['spec']['template']['spec'].get('timeoutSeconds','')")
CC=$(jqq "d['spec']['template']['spec'].get('containerConcurrency','')")
[ -n "$SA" ] && pass "runtime service account: $SA" || fail "no explicit runtime service account"
[ "$SA" = "$EXPECTED_RUNTIME_SA" ] \
  && pass "runtime service account matches EXPECTED_RUNTIME_SA" \
  || fail "runtime service account mismatch: expected $EXPECTED_RUNTIME_SA"
[ "$TO" = "480" ] && pass "timeout 480s" || fail "timeout is $TO, expected 480"
[ "$CC" = "1" ] && pass "concurrency 1" || fail "concurrency is $CC, expected 1"

echo
echo "=== 4. Grok disabled (names and flags only, no secret values) ==="
GROK=$(printf "%s" "$DESCRIBE" | python3 -c "
import sys, json
d = json.load(sys.stdin)
env = d['spec']['template']['spec']['containers'][0].get('env', [])
print(next((e.get('value','') for e in env if e.get('name') == 'GROK_PROXY_ENABLED'), '<unset>'))
" 2>/dev/null)
case "$GROK" in
  false|False|FALSE) pass "GROK_PROXY_ENABLED=$GROK" ;;
  "<unset>")         pass "GROK_PROXY_ENABLED unset (code default is disabled)" ;;
  *)                 fail "GROK_PROXY_ENABLED=$GROK -- Grok is not disabled" ;;
esac
if printf "%s" "$DESCRIBE" | grep -q "GROK_CHAT_ENABLED"; then
  fail "GROK_CHAT_ENABLED set on the worker; it is a no-op here and is false assurance"
else
  pass "no no-op GROK_CHAT_ENABLED on the worker"
fi

echo
echo "=== 5. Required variables present (names only, values never printed) ==="
NAMES=$(printf "%s" "$DESCRIBE" | python3 -c "
import sys, json
d = json.load(sys.stdin)
c = d['spec']['template']['spec']['containers'][0]
print(' '.join(sorted(e.get('name','') for e in c.get('env', []))))
" 2>/dev/null)
# SCANNER_API_KEY is intentionally absent: /scan-job does not use it.
for v in BASE44_APP_ID TASKS_INVOKER_SERVICE_ACCOUNT SCAN_EVIDENCE_SIGNING_KEY; do
  printf "%s" "$NAMES" | grep -qw "$v" && pass "$v present" || fail "$v missing"
done
INVOKER_ENV=$(printf "%s" "$DESCRIBE" | python3 -c "
import sys, json
d = json.load(sys.stdin)
env = d['spec']['template']['spec']['containers'][0].get('env', [])
print(next((e.get('value','') for e in env if e.get('name') == 'TASKS_INVOKER_SERVICE_ACCOUNT'), ''))
" 2>/dev/null)
[ "$INVOKER_ENV" = "$EXPECTED_INVOKER_SA" ] \
  && pass "TASKS_INVOKER_SERVICE_ACCOUNT matches EXPECTED_INVOKER_SA" \
  || fail "TASKS_INVOKER_SERVICE_ACCOUNT does not match EXPECTED_INVOKER_SA"
# Secrets must arrive by reference, not as literals.
SECRET_REFS=$(printf "%s" "$DESCRIBE" | python3 -c "
import sys, json
d = json.load(sys.stdin)
c = d['spec']['template']['spec']['containers'][0]
print(sum(1 for e in c.get('env', []) if 'valueFrom' in e))
" 2>/dev/null)
# Exactly one secret is required by the durable path: the signing key.
[ "${SECRET_REFS:-0}" -ge 1 ] \
  && pass "secret injected by reference ($SECRET_REFS valueFrom entr(y/ies))" \
  || fail "expected >=1 secret reference; the signing key may be a plaintext env var"

# The signing key reference must match the pinned secret NAME and numeric
# VERSION exactly. Metadata only: no payload is read. Fail closed on a missing,
# malformed, plaintext, 'latest' or mismatched reference.
SIGNING_REF=$(printf "%s" "$DESCRIBE" | python3 -c "
import sys, json
d = json.load(sys.stdin)
c = d['spec']['template']['spec']['containers'][0]
e = next((x for x in c.get('env', []) if x.get('name') == 'SCAN_EVIDENCE_SIGNING_KEY'), None)
if e is None:
    print('ABSENT'); raise SystemExit
if 'value' in e:
    print('PLAINTEXT'); raise SystemExit
r = e.get('valueFrom', {}).get('secretKeyRef') or {}
name, key = str(r.get('name','')), str(r.get('key',''))
print('MALFORMED' if not name or not key else 'REF %s %s' % (name, key))
" 2>/dev/null)
case "$SIGNING_REF" in
  "ABSENT")    fail "SCAN_EVIDENCE_SIGNING_KEY absent from the revision" ;;
  "PLAINTEXT") fail "SCAN_EVIDENCE_SIGNING_KEY is a plaintext env var, not a secret reference" ;;
  "MALFORMED") fail "SCAN_EVIDENCE_SIGNING_KEY secretKeyRef is missing its name or version" ;;
  "REF "*)
    GOT_SECRET=$(printf "%s" "$SIGNING_REF" | awk '{print $2}')
    GOT_VERSION=$(printf "%s" "$SIGNING_REF" | awk '{print $3}')
    case "$GOT_VERSION" in
      latest|LATEST) fail "signing key mounted at ':latest'; the release requires a pinned numeric version" ;;
      ''|*[!0-9]*)   fail "signing key version '$GOT_VERSION' is not numeric" ;;
      *)
        [ "$GOT_SECRET" = "$EXPECTED_SIGNING_SECRET" ] \
          && pass "signing secret name matches ($GOT_SECRET)" \
          || fail "signing secret name is '$GOT_SECRET', expected '$EXPECTED_SIGNING_SECRET'"
        [ "$GOT_VERSION" = "$EXPECTED_SIGNING_VERSION" ] \
          && pass "signing secret version pinned to $GOT_VERSION" \
          || fail "signing secret version is '$GOT_VERSION', expected '$EXPECTED_SIGNING_VERSION'"
        ;;
    esac ;;
  *) fail "signing key reference could not be read from the revision (describe unparsable)" ;;
esac

echo
echo "=== 6. Cloud Tasks queue contract ==="
case "$EXPECTED_SCAN_QUEUE_CONCURRENCY" in
  1|3|5|10) ;;
  *) fail "EXPECTED_SCAN_QUEUE_CONCURRENCY must be exactly 1, 3, 5, or 10" ;;
esac
SCAN_QUEUE_JSON=$(gcloud tasks queues describe "$TASKS_QUEUE" --location="$REGION" --project="$PROJECT" --format=json 2>/dev/null || true)
DRAIN_QUEUE_JSON=$(gcloud tasks queues describe "$DRAIN_QUEUE" --location="$REGION" --project="$PROJECT" --format=json 2>/dev/null || true)
if [ -z "$SCAN_QUEUE_JSON" ]; then
  fail "scan queue $TASKS_QUEUE could not be described"
else
  SCAN_QUEUE_CHECK=$(SCAN_QUEUE_JSON="$SCAN_QUEUE_JSON" EXPECTED_SCAN_QUEUE_CONCURRENCY="$EXPECTED_SCAN_QUEUE_CONCURRENCY" python3 -c '
import json,os
q=json.loads(os.environ["SCAN_QUEUE_JSON"]); expected=int(os.environ["EXPECTED_SCAN_QUEUE_CONCURRENCY"])
r=q.get("rateLimits") or {}; retry=q.get("retryConfig") or {}
ok=(str(q.get("state") or "") in {"RUNNING","PAUSED"}
    and int(r.get("maxConcurrentDispatches") or 0)==expected
    and float(r.get("maxDispatchesPerSecond") or 0)==float(expected)
    and int(retry.get("maxAttempts") or 0)==3
    and str(retry.get("minBackoff") or "")=="10s"
    and str(retry.get("maxBackoff") or "")=="300s"
    and int(retry.get("maxDoublings") or 0)==3)
print("OK" if ok else "BAD")
')
  [ "$SCAN_QUEUE_CHECK" = "OK" ] && pass "scan queue matches beta concurrency/retry contract" || fail "scan queue differs from beta concurrency/retry contract"
fi
if [ -z "$DRAIN_QUEUE_JSON" ]; then
  fail "drain queue $DRAIN_QUEUE could not be described"
else
  DRAIN_QUEUE_CHECK=$(DRAIN_QUEUE_JSON="$DRAIN_QUEUE_JSON" python3 -c '
import json,os
q=json.loads(os.environ["DRAIN_QUEUE_JSON"]); r=q.get("rateLimits") or {}; retry=q.get("retryConfig") or {}
ok=(str(q.get("state") or "") in {"RUNNING","PAUSED"}
    and int(r.get("maxConcurrentDispatches") or 0)==5
    and float(r.get("maxDispatchesPerSecond") or 0)==5.0
    and int(retry.get("maxAttempts") or 0)==100
    and str(retry.get("maxRetryDuration") or "")=="14400s"
    and str(retry.get("minBackoff") or "")=="30s"
    and str(retry.get("maxBackoff") or "")=="180s"
    and int(retry.get("maxDoublings") or 0)==3)
print("OK" if ok else "BAD")
')
  [ "$DRAIN_QUEUE_CHECK" = "OK" ] && pass "drain queue matches independent watchdog contract" || fail "drain queue differs from independent watchdog contract"
fi

echo
echo "=== 7. Base44 deployed function and authority-schema inventory ==="
if ! command -v "$NODE_BIN" >/dev/null 2>&1 && [ ! -x "$NODE_BIN" ]; then
  fail "NODE_BIN is unavailable; deployed Base44 packages cannot be compared"
elif [ ! -e "$BASE44_PULLED_FUNCTIONS_DIR/." ]; then
  fail "BASE44_PULLED_FUNCTIONS_DIR does not exist"
elif [ ! -e "$BASE44_PULLED_ENTITIES_DIR/." ]; then
  fail "BASE44_PULLED_ENTITIES_DIR does not exist"
elif "$NODE_BIN" scripts/base44_release_manifest.mjs compare \
  "$BASE44_PULLED_FUNCTIONS_DIR" "$BASE44_PULLED_ENTITIES_DIR" >/dev/null; then
  pass "all six deployed functions and three authority entity schemas match the candidate manifest"
else
  fail "deployed Base44 function/entity inventory is missing or differs from the candidate"
fi

echo
echo "=== Result ==="
if [ "$FAILED" -gt 0 ]; then
  echo "POST-DEPLOY VERIFICATION FAILED ($FAILED check(s))"
  exit 1
fi
echo "POST-DEPLOY VERIFICATION PASSED"
exit 0
