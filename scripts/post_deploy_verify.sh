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
#   WORKER_SERVICE=... REGION=... PROJECT=... CANDIDATE_REVISION=... \
#   EXPECTED_IMAGE=... EXPECTED_RUNTIME_SA=... EXPECTED_INVOKER_SA=... \
#   EXPECTED_SIGNING_SECRET=... EXPECTED_SIGNING_VERSION=... \
#   [BASE44_APP_ID=...] \
#   bash scripts/post_deploy_verify.sh
#
# All EXPECTED_* inputs above are REQUIRED, as is CANDIDATE_REVISION.
#
# CANDIDATE_REVISION names the exact revision under test. Every revision-scoped
# check reads THAT revision, never the service template. The template describes
# what the service would deploy next; a candidate held at 0% traffic is a
# different object, and verifying the template would pass a candidate that was
# never actually created with those settings.
#
# The candidate must use the exact image and runtime/invoker identities and
# mount SCAN_EVIDENCE_SIGNING_KEY from exactly that secret at exactly that
# numeric version. Metadata only -- the payload is never accessed.

set -uo pipefail

FAILED=0
pass() { printf "  PASS  %s\n" "$1"; }
fail() { printf "  FAIL  %s\n" "$1"; FAILED=$((FAILED + 1)); }
skip() { printf "  SKIP  %s\n" "$1"; }

: "${WORKER_SERVICE:=}"
: "${REGION:=}"
: "${PROJECT:=}"
: "${CANDIDATE_REVISION:=}"
: "${EXPECTED_IMAGE:=}"
: "${EXPECTED_RUNTIME_SA:=}"
: "${EXPECTED_INVOKER_SA:=}"
: "${BASE44_APP_ID:=}"
: "${EXPECTED_SIGNING_SECRET:=}"
: "${EXPECTED_SIGNING_VERSION:=}"

if [ -z "$WORKER_SERVICE" ] || [ -z "$REGION" ] || [ -z "$PROJECT" ]; then
  echo "WORKER_SERVICE, REGION and PROJECT are required. Nothing is guessed."
  exit 2
fi
if [ -z "$CANDIDATE_REVISION" ]; then
  echo "CANDIDATE_REVISION is required: name the exact revision under test."
  echo "Verifying the service template instead would check what the service would"
  echo "deploy next, not the candidate currently held at 0% traffic."
  exit 2
fi
if [ -z "$EXPECTED_IMAGE" ] || [ -z "$EXPECTED_RUNTIME_SA" ] || [ -z "$EXPECTED_INVOKER_SA" ] || \
   [ -z "$EXPECTED_SIGNING_SECRET" ] || [ -z "$EXPECTED_SIGNING_VERSION" ]; then
  echo "EXPECTED_IMAGE, EXPECTED_RUNTIME_SA, EXPECTED_INVOKER_SA, EXPECTED_SIGNING_SECRET and EXPECTED_SIGNING_VERSION are required."
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

if ! REVISION_JSON=$(gcloud run revisions describe "$CANDIDATE_REVISION" \
  --region="$REGION" --project="$PROJECT" --format=json 2>/dev/null) || [ -z "$REVISION_JSON" ]; then
  echo "Could not describe revision $CANDIDATE_REVISION in $REGION."
  echo "The candidate must exist before it can be verified."
  exit 2
fi

# jqq reads the SERVICE (privacy, IAM, URL, traffic).
# rq  reads the CANDIDATE REVISION (image, identity, limits, env, secrets).
jqq() { printf "%s" "$DESCRIBE" | python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null; }
rq()  { printf "%s" "$REVISION_JSON" | python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null; }

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
echo "=== 2. Candidate revision and image identity ==="
pass "candidate under test: $CANDIDATE_REVISION"

# The candidate must be Ready in its own right. latestReadyRevisionName is a
# service-level pointer and can name a different revision entirely while the
# candidate is held at 0%, so it is never used as the subject here.
READY=$(rq "next((c.get('status','') for c in d.get('status',{}).get('conditions',[]) if c.get('type')=='Ready'), '')")
[ "$READY" = "True" ] \
  && pass "candidate revision is Ready" \
  || fail "candidate revision is not Ready (Ready=${READY:-<none>})"

SERVICE_LATEST_READY=$(jqq "d.get('status',{}).get('latestReadyRevisionName','')")
[ -n "$SERVICE_LATEST_READY" ] && skip "service latestReadyRevisionName: $SERVICE_LATEST_READY (context only, not verified)"

# The candidate must still hold zero traffic at verification time.
CANDIDATE_PCT=$(jqq "sum(int(t.get('percent') or 0) for t in d.get('status',{}).get('traffic',[]) if (t.get('revisionName') or t.get('revision'))=='$CANDIDATE_REVISION')")
[ "${CANDIDATE_PCT:-0}" = "0" ] \
  && pass "candidate holds 0% traffic" \
  || fail "candidate already serves ${CANDIDATE_PCT}% traffic; verification must precede promotion"

# Image identity is proven digest-to-digest. An image has two representations --
# the tag supplied at deploy time and the digest Cloud Run resolves it to -- and
# which one appears in an API response depends on the object being read. A
# byte-for-byte comparison that lands on opposite representations can only ever
# fail, in either direction. Both sides are therefore reduced to a digest first.
REV_IMAGE=$(rq "d['spec']['containers'][0].get('image','')")
REV_DIGEST=$(rq "d.get('status',{}).get('imageDigest','')")
# Cloud Run normally records the resolved digest in status.imageDigest. When a
# revision was created from a digest reference the same proof is already carried
# on spec.containers[0].image, so that is the only accepted fallback. A tag is
# never accepted as a digest.
if [ -z "$REV_DIGEST" ]; then
  case "$REV_IMAGE" in
    *@sha256:*) REV_DIGEST="$REV_IMAGE" ;;
  esac
fi
[ -n "$REV_IMAGE" ] && pass "candidate image reference: $REV_IMAGE" || fail "candidate has no image reference"
[ -n "$REV_DIGEST" ] && pass "candidate resolved digest: $REV_DIGEST" || fail "candidate has no resolved digest"

# Reduce the expectation to a digest. A digest expectation is used as-is; a tag
# expectation is resolved through Artifact Registry, which PROVES the tag points
# at that digest rather than assuming it. Identity is never weakened to
# "same repository" or "any tag".
case "$EXPECTED_IMAGE" in
  *@sha256:*)
    EXPECTED_DIGEST="${EXPECTED_IMAGE##*@}"
    EXPECTED_SOURCE="supplied digest"
    ;;
  *)
    EXPECTED_DIGEST=$(gcloud artifacts docker images describe "$EXPECTED_IMAGE" \
      --project="$PROJECT" --format='value(image_summary.digest)' 2>/dev/null)
    EXPECTED_SOURCE="tag $EXPECTED_IMAGE resolved via Artifact Registry"
    ;;
esac

if [ -z "$EXPECTED_DIGEST" ]; then
  fail "could not resolve EXPECTED_IMAGE to a digest ($EXPECTED_IMAGE)"
else
  pass "expected digest: $EXPECTED_DIGEST ($EXPECTED_SOURCE)"
  # Compare only the digest. The registry path is checked separately so a digest
  # match in a DIFFERENT repository still fails.
  ACTUAL_DIGEST="${REV_DIGEST##*@}"
  [ "$ACTUAL_DIGEST" = "${EXPECTED_DIGEST##*@}" ] \
    && pass "candidate image digest matches expected" \
    || fail "image digest mismatch: candidate $ACTUAL_DIGEST, expected ${EXPECTED_DIGEST##*@}"

  EXPECTED_REPO="${EXPECTED_IMAGE%%@*}"; EXPECTED_REPO="${EXPECTED_REPO%%:*}"
  ACTUAL_REPO="${REV_IMAGE%%@*}"; ACTUAL_REPO="${ACTUAL_REPO%%:*}"
  [ "$ACTUAL_REPO" = "$EXPECTED_REPO" ] \
    && pass "candidate image repository matches expected" \
    || fail "image repository mismatch: candidate $ACTUAL_REPO, expected $EXPECTED_REPO"
fi

echo
echo "=== 3. Runtime configuration ==="
SA=$(rq "d['spec'].get('serviceAccountName','')")
TO=$(rq "d['spec'].get('timeoutSeconds','')")
CC=$(rq "d['spec'].get('containerConcurrency','')")
[ -n "$SA" ] && pass "runtime service account: $SA" || fail "no explicit runtime service account"
[ "$SA" = "$EXPECTED_RUNTIME_SA" ] \
  && pass "runtime service account matches EXPECTED_RUNTIME_SA" \
  || fail "runtime service account mismatch: expected $EXPECTED_RUNTIME_SA"
[ "$TO" = "480" ] && pass "timeout 480s" || fail "timeout is $TO, expected 480"
[ "$CC" = "1" ] && pass "concurrency 1" || fail "concurrency is $CC, expected 1"

echo
echo "=== 4. Grok disabled (names and flags only, no secret values) ==="
GROK=$(printf "%s" "$REVISION_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
env = d['spec']['containers'][0].get('env', [])
print(next((e.get('value','') for e in env if e.get('name') == 'GROK_PROXY_ENABLED'), '<unset>'))
" 2>/dev/null)
case "$GROK" in
  false|False|FALSE) pass "GROK_PROXY_ENABLED=$GROK" ;;
  "<unset>")         pass "GROK_PROXY_ENABLED unset (code default is disabled)" ;;
  *)                 fail "GROK_PROXY_ENABLED=$GROK -- Grok is not disabled" ;;
esac
if printf "%s" "$REVISION_JSON" | grep -q "GROK_CHAT_ENABLED"; then
  fail "GROK_CHAT_ENABLED set on the worker; it is a no-op here and is false assurance"
else
  pass "no no-op GROK_CHAT_ENABLED on the worker"
fi

echo
echo "=== 5. Required variables present (names only, values never printed) ==="
NAMES=$(printf "%s" "$REVISION_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
c = d['spec']['containers'][0]
print(' '.join(sorted(e.get('name','') for e in c.get('env', []))))
" 2>/dev/null)
# SCANNER_API_KEY is intentionally absent: /scan-job does not use it.
for v in BASE44_APP_ID TASKS_INVOKER_SERVICE_ACCOUNT SCAN_EVIDENCE_SIGNING_KEY; do
  printf "%s" "$NAMES" | grep -qw "$v" && pass "$v present" || fail "$v missing"
done
INVOKER_ENV=$(printf "%s" "$REVISION_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
env = d['spec']['containers'][0].get('env', [])
print(next((e.get('value','') for e in env if e.get('name') == 'TASKS_INVOKER_SERVICE_ACCOUNT'), ''))
" 2>/dev/null)
[ "$INVOKER_ENV" = "$EXPECTED_INVOKER_SA" ] \
  && pass "TASKS_INVOKER_SERVICE_ACCOUNT matches EXPECTED_INVOKER_SA" \
  || fail "TASKS_INVOKER_SERVICE_ACCOUNT does not match EXPECTED_INVOKER_SA"
# Secrets must arrive by reference, not as literals.
SECRET_REFS=$(printf "%s" "$REVISION_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
c = d['spec']['containers'][0]
print(sum(1 for e in c.get('env', []) if 'valueFrom' in e))
" 2>/dev/null)
# Exactly one secret is required by the durable path: the signing key.
[ "${SECRET_REFS:-0}" -ge 1 ] \
  && pass "secret injected by reference ($SECRET_REFS valueFrom entr(y/ies))" \
  || fail "expected >=1 secret reference; the signing key may be a plaintext env var"

# The signing key reference must match the pinned secret NAME and numeric
# VERSION exactly. Metadata only: no payload is read. Fail closed on a missing,
# malformed, plaintext, 'latest' or mismatched reference.
SIGNING_REF=$(printf "%s" "$REVISION_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
c = d['spec']['containers'][0]
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
