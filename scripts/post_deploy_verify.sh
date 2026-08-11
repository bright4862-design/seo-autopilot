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
#   EXPECTED_SIGNING_SECRET=... EXPECTED_SIGNING_VERSION=... \
#   [EXPECTED_IMAGE=...] [BASE44_APP_ID=...] \
#   bash scripts/post_deploy_verify.sh
#
# EXPECTED_SIGNING_SECRET / EXPECTED_SIGNING_VERSION are REQUIRED. The deployed
# revision must mount SCAN_EVIDENCE_SIGNING_KEY from exactly that secret at
# exactly that numeric version. Metadata only -- the payload is never accessed.

set -uo pipefail

FAILED=0
pass() { printf "  PASS  %s\n" "$1"; }
fail() { printf "  FAIL  %s\n" "$1"; FAILED=$((FAILED + 1)); }
skip() { printf "  SKIP  %s\n" "$1"; }

: "${WORKER_SERVICE:=}"
: "${REGION:=}"
: "${PROJECT:=}"
: "${EXPECTED_IMAGE:=}"
: "${BASE44_APP_ID:=}"
: "${EXPECTED_SIGNING_SECRET:=}"
: "${EXPECTED_SIGNING_VERSION:=}"

if [ -z "$WORKER_SERVICE" ] || [ -z "$REGION" ] || [ -z "$PROJECT" ]; then
  echo "WORKER_SERVICE, REGION and PROJECT are required. Nothing is guessed."
  exit 2
fi
if [ -z "$EXPECTED_SIGNING_SECRET" ] || [ -z "$EXPECTED_SIGNING_VERSION" ]; then
  echo "EXPECTED_SIGNING_SECRET and EXPECTED_SIGNING_VERSION are required."
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
POLICY=$(gcloud run services get-iam-policy "$WORKER_SERVICE" \
  --region="$REGION" --project="$PROJECT" --format=json 2>/dev/null)
if [ -n "$POLICY" ]; then
  if printf "%s" "$POLICY" | grep -qE '"(allUsers|allAuthenticatedUsers)"'; then
    fail "service is PUBLIC (allUsers/allAuthenticatedUsers hold an IAM role)"
  else
    pass "no public principal in the IAM policy"
  fi
else
  skip "IAM policy unreadable (needs run.services.getIamPolicy)"
fi

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
if [ -n "$EXPECTED_IMAGE" ]; then
  [ "$IMG" = "$EXPECTED_IMAGE" ] \
    && pass "image matches EXPECTED_IMAGE" \
    || fail "image mismatch: expected $EXPECTED_IMAGE"
else
  skip "EXPECTED_IMAGE not supplied; identity not pinned"
fi

echo
echo "=== 3. Runtime configuration ==="
SA=$(jqq "d['spec']['template']['spec'].get('serviceAccountName','')")
TO=$(jqq "d['spec']['template']['spec'].get('timeoutSeconds','')")
CC=$(jqq "d['spec']['template']['spec'].get('containerConcurrency','')")
[ -n "$SA" ] && pass "runtime service account: $SA" || fail "no explicit runtime service account"
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
echo "=== 6. Base44 function presence (manual) ==="
skip "durableScanWorkerControl / persistDurableScanAuthority presence must be confirmed in the Base44 dashboard; no read-only CLI check exists"

echo
echo "=== Result ==="
if [ "$FAILED" -gt 0 ]; then
  echo "POST-DEPLOY VERIFICATION FAILED ($FAILED check(s))"
  exit 1
fi
echo "POST-DEPLOY VERIFICATION PASSED"
exit 0
