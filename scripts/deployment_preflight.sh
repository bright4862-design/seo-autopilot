#!/usr/bin/env bash
# Static deployment preflight for the durable Standard 150 release.
#
# Read-only. Makes no GCP, Base44, or network call and mutates nothing.
#
# SECRET SAFETY: every credential check reports PRESENT/ABSENT only. No value,
# no prefix, no length, no fingerprint is ever printed. Do not add one.
#
# Reports TWO INDEPENDENT verdicts, so a missing local tool can never disguise
# whether the repository source itself is green:
#
#   SOURCE READY | SOURCE BLOCKED
#   DEPLOYMENT ENVIRONMENT READY | DEPLOYMENT ENVIRONMENT BLOCKED
#
# Exit 0 = source ready AND environment ready
#      1 = source blocked (a real defect, regardless of environment)
#      2 = source ready, environment blocked (nothing wrong with the repo)

set -uo pipefail

SRC_FAIL=0
ENV_FAIL=0

pass() { printf "  PASS  %s\n" "$1"; }
fail() { printf "  FAIL  %s\n" "$1"; SRC_FAIL=$((SRC_FAIL + 1)); }
envm() { printf "  MISS  %s\n" "$1"; ENV_FAIL=$((ENV_FAIL + 1)); }

need_file() { [ -f "$1" ] && pass "$2" || fail "$2 (missing $1)"; }
has() { grep -q -- "$1" "$2" 2>/dev/null; }

WORKER_BUILD="cloudbuild.durable-worker.yaml"
TASKS="base44/functions/startStandardScanJob/cloudTasks.js"
WORKER_SRC="scanner-api/app/main.py"

echo "=== 1. Base44 package integrity ==="
if node scripts/base44_release_manifest.mjs verify >/dev/null 2>&1; then
  pass "release packages portable, closed, pinned, symlink-free"
else
  fail "package integrity failed (node scripts/base44_release_manifest.mjs verify)"
fi

echo
echo "=== 2. Worker deployment artifact ==="
need_file "Dockerfile" "Dockerfile present"
need_file "$WORKER_BUILD" "worker build artifact present"
if [ -f "$WORKER_BUILD" ]; then
  has "--no-allow-unauthenticated" "$WORKER_BUILD" \
    && pass "worker deploys private (--no-allow-unauthenticated)" \
    || fail "worker not private; app-level invoker check is forgeable without it"
  has "--service-account=" "$WORKER_BUILD" \
    && pass "explicit runtime service account" \
    || fail "no explicit runtime service account (would inherit default compute SA)"
  has "--timeout=480" "$WORKER_BUILD" \
    && pass "Cloud Run timeout 480s" || fail "Cloud Run timeout is not 480s"
  has "--concurrency=1" "$WORKER_BUILD" \
    && pass "concurrency 1" || fail "concurrency is not 1"
  has "--no-traffic" "$WORKER_BUILD" \
    && pass "no traffic migration on deploy" || fail "deploy would migrate traffic"
  # The worker reads GROK_PROXY_ENABLED (scanner-api/app/main.py).
  # GROK_CHAT_ENABLED belongs to the Base44 grokChat function and is a no-op
  # on this service -- setting it here would be false assurance.
  has "GROK_PROXY_ENABLED=false" "$WORKER_BUILD" \
    && pass "Grok disabled with the variable the worker actually reads" \
    || fail "GROK_PROXY_ENABLED=false not set on the worker"
  if grep -v '^\s*#' "$WORKER_BUILD" | grep -q "GROK_CHAT_ENABLED"; then
    fail "GROK_CHAT_ENABLED set on the worker; that variable is only read by the Base44 grokChat function"
  else
    pass "no no-op GROK_CHAT_ENABLED on the worker"
  fi

  # Required worker variables, per docs/standard150-deployment-contract.md.
  # Must appear on the --set-env-vars line. A bare file-wide match would be
  # satisfied by the substitution-guard step, hiding a missing deploy value.
  ENVLINE=$(grep -- "--set-env-vars" "$WORKER_BUILD" 2>/dev/null || true)
  for v in BASE44_APP_ID BASE44_API_URL TASKS_INVOKER_SERVICE_ACCOUNT; do
    printf "%s" "$ENVLINE" | grep -qE "[,=]${v}=" \
      && pass "$v supplied on the deploy line" \
      || fail "$v not on --set-env-vars; see docs/standard150-deployment-contract.md"
  done

  # Secrets by reference only.
  has "--set-secrets=" "$WORKER_BUILD" \
    && pass "secrets injected from Secret Manager by name" \
    || fail "no --set-secrets; signing key and scanner key would be unset"
  # SCAN_EVIDENCE_SIGNING_KEY is the only secret /scan-job needs.
  # SCANNER_API_KEY guards sibling routes this worker does not serve.
  # The signing key must be pinned to an exact numeric version. "latest"
  # re-resolves at instance start, so a new secret version would change what an
  # already-verified revision reads with no revision change to point at.
  has '_SIGNING_KEY_VERSION: ""' "$WORKER_BUILD" \
    && pass "_SIGNING_KEY_VERSION is a required, fail-closed substitution" \
    || fail "_SIGNING_KEY_VERSION missing or not fail-closed in the build artifact"
  has '"_SIGNING_KEY_VERSION=${_SIGNING_KEY_VERSION}"' "$WORKER_BUILD" \
    && pass "_SIGNING_KEY_VERSION covered by the missing-substitution guard" \
    || fail "_SIGNING_KEY_VERSION not covered by the missing-substitution guard"
  has 'SCAN_EVIDENCE_SIGNING_KEY=${_SIGNING_KEY_SECRET}:${_SIGNING_KEY_VERSION}' "$WORKER_BUILD" \
    && pass "signing secret binds both name and version substitutions" \
    || fail "signing secret does not bind ${_SIGNING_KEY_SECRET}:${_SIGNING_KEY_VERSION}"
  # Executable lines only: the header documents why latest is prohibited.
  if grep -v '^[[:space:]]*#' "$WORKER_BUILD" | grep -q -- ':latest'; then
    fail "executable ':latest' in the build artifact; the release must pin a numeric version"
  else
    pass "no executable ':latest' in the build artifact"
  fi

  # Manual `gcloud builds submit` does not reliably populate the built-in
  # $COMMIT_SHA. The release therefore requires one explicit full SHA and uses
  # that substitution for every image reference.
  has '_RELEASE_SHA: ""' "$WORKER_BUILD" \
    && pass "_RELEASE_SHA is a required, fail-closed substitution" \
    || fail "_RELEASE_SHA missing or not fail-closed in the build artifact"
  has '"_RELEASE_SHA=${_RELEASE_SHA}"' "$WORKER_BUILD" \
    && pass "_RELEASE_SHA covered by the missing-substitution guard" \
    || fail "_RELEASE_SHA not covered by the missing-substitution guard"
  has '${_IMAGE}:${_RELEASE_SHA}' "$WORKER_BUILD" \
    && pass "image identity is pinned to _RELEASE_SHA" \
    || fail "image identity is not pinned to _RELEASE_SHA"
  if grep -v '^[[:space:]]*#' "$WORKER_BUILD" | grep -q '\$COMMIT_SHA'; then
    fail "executable \$COMMIT_SHA in the build artifact; manual builds can replace it with an empty string"
  else
    pass "no executable \$COMMIT_SHA dependency in the build artifact"
  fi

  for v in SCAN_EVIDENCE_SIGNING_KEY; do
    if grep -v '^\s*#' "$WORKER_BUILD" | grep -q -- "--set-env-vars.*$v"; then
      fail "$v passed via --set-env-vars; that stores plaintext in the revision"
    else
      pass "$v not passed as a plaintext env var"
    fi
    grep -v '^\s*#' "$WORKER_BUILD" | grep -q -- "--set-secrets.*$v" \
      && pass "$v injected as a secret reference" \
      || fail "$v not injected from Secret Manager"
  done
  # The worker must not be handed the sibling-route key it never uses.
  if grep -v '^\s*#' "$WORKER_BUILD" | grep -q "SCANNER_API_KEY"; then
    fail "SCANNER_API_KEY supplied to the durable worker; /scan-job never calls require_scanner_api_key()"
  else
    pass "SCANNER_API_KEY not supplied (not used by /scan-job)"
  fi
  has "_WORKER_SERVICE" "$WORKER_BUILD" \
    && pass "worker service name is a required parameter" \
    || fail "worker service name is not parameterized"
  has "Refusing to build" "$WORKER_BUILD" \
    && pass "build fails closed when a parameter is missing" \
    || fail "build does not fail closed on missing parameters"
  # Must not redeploy the existing scanner service.
  if [ -f cloudbuild.yaml ]; then
    # Comment lines are excluded: the artifact's header names the existing
    # service precisely to say it must not be reused.
    existing=$(grep -oE "seo-autopilot-[0-9]+" cloudbuild.yaml 2>/dev/null | head -1 || true)
    if [ -n "$existing" ] && grep -v '^\s*#' "$WORKER_BUILD" | grep -q "$existing" 2>/dev/null; then
      fail "worker artifact references the existing scanner service ($existing)"
    else
      pass "worker artifact does not target the existing scanner service"
    fi
  fi
fi

echo
echo "=== 3. Route, deadline, OIDC ==="
if [ -f "$WORKER_SRC" ]; then
  has "/scan-job" "$WORKER_SRC" && pass "/scan-job route defined" || fail "/scan-job route missing"
  has "TASKS_INVOKER_SERVICE_ACCOUNT" "$WORKER_SRC" \
    && pass "worker checks invoker service account" || fail "no invoker identity check"
  # Truthfulness: the app must not claim verification it does not perform.
  if grep -q "does NOT verify the token signature" "$WORKER_SRC" 2>/dev/null; then
    pass "OIDC docs state the real trust boundary (IAM validates; app checks email)"
  else
    fail "OIDC documentation overstates what the application validates"
  fi
else
  fail "$WORKER_SRC missing"
fi

if [ -f "$TASKS" ]; then
  has 'export const WORKER_DISPATCH_DEADLINE = "480s"' "$TASKS" \
    && has 'dispatchDeadline: WORKER_DISPATCH_DEADLINE' "$TASKS" \
    && pass "dispatchDeadline 480s" || fail "dispatchDeadline not bound to 480s"
  has "oidcToken" "$TASKS" && pass "task carries OIDC token" || fail "task has no OIDC token"
  has "serviceAccountEmail" "$TASKS" && pass "OIDC invoker SA set" || fail "OIDC has no invoker SA"
  has "audience" "$TASKS" && pass "OIDC audience set" || fail "OIDC has no audience"
  has 'standard150-${safeScanId(scanId)}-a${normalizeAttemptCount(attemptCount)}' "$TASKS" \
    && pass "task name deterministic per (scan_id, attempt)" || fail "task name not attempt-bound"
  # One deterministic auth route only.
  # Ignore comment lines: the file documents why the fallback was removed.
  if grep -v '^\s*//' "$TASKS" | grep -q "GCP_ACCESS_TOKEN" 2>/dev/null; then
    fail "GCP_ACCESS_TOKEN fallback present (second, expiring credential path)"
  else
    pass "single deterministic auth route (no direct-token fallback)"
  fi
  has "tasks_credentials_not_configured" "$TASKS" \
    && pass "missing-key failure code preserved" || fail "missing-key failure code absent"
  has "tasks_token_mint_failed" "$TASKS" \
    && pass "mint-failure distinguished from missing key" || fail "mint failure not distinguished"
  has 'tasks_http_${response.status}' "$TASKS" \
    && pass "HTTP-derived codes preserved (401/403 stay distinct)" || fail "HTTP status codes not preserved"
else
  fail "$TASKS missing"
fi

echo
echo "=== 3b. Deployment contract ==="
if [ -f docs/standard150-deployment-contract.md ]; then
  pass "deployment contract present"
  grep -q "GROK_PROXY_ENABLED" docs/standard150-deployment-contract.md \
    && pass "contract documents the worker Grok variable" \
    || fail "contract does not document GROK_PROXY_ENABLED"
else
  fail "docs/standard150-deployment-contract.md missing"
fi
[ -f scripts/post_deploy_verify.sh ] && pass "post-deploy verification script present" \
  || fail "scripts/post_deploy_verify.sh missing"

echo
echo "=== 4. Toolchain presence ==="
command -v node >/dev/null 2>&1 && pass "node $(node --version)" || envm "node not installed"
command -v python3 >/dev/null 2>&1 && pass "python3 present" || envm "python3 not installed"
command -v gcloud >/dev/null 2>&1 && pass "gcloud present" || envm "gcloud not installed"
if command -v docker >/dev/null 2>&1; then
  # Bounded: an unreachable daemon otherwise blocks until its own timeout.
  if timeout 10 docker info >/dev/null 2>&1; then pass "docker daemon reachable"
  else envm "docker daemon unreachable (no local image build)"; fi
else
  envm "docker not installed (no local image build)"
fi

echo
echo "=== 5. Credential presence (names only, values never read) ==="
for var in GCP_DEPLOY_SA_KEY GCP_SERVICE_ACCOUNT_KEY SCAN_EVIDENCE_SIGNING_KEY \
           SCANNER_API_URL SCANNER_API_KEY TASKS_INVOKER_SERVICE_ACCOUNT; do
  if [ -n "${!var:-}" ]; then pass "$var PRESENT"; else envm "$var ABSENT"; fi
done

echo
echo "=== 6. Deployment parameters (must be supplied explicitly) ==="
for var in WORKER_SERVICE REGION IMAGE RUNTIME_SA INVOKER_SA TASKS_QUEUE \
           BASE44_APP_ID BASE44_API_URL SIGNING_KEY_SECRET SIGNING_KEY_VERSION \
           RELEASE_SHA; do
  if [ -n "${!var:-}" ]; then pass "$var supplied"; else envm "$var not supplied"; fi
done

# SIGNING_KEY_VERSION must be numeric. "latest" is prohibited for the immutable
# release. An unsupplied value is an environment gap; a malformed one is a
# source-level failure, because it would deploy an unpinned mount.
if [ -n "${SIGNING_KEY_VERSION:-}" ]; then
  case "$SIGNING_KEY_VERSION" in
    latest|LATEST) fail "SIGNING_KEY_VERSION='latest' is prohibited; pin a numeric enabled version" ;;
    ''|*[!0-9]*)   fail "SIGNING_KEY_VERSION='$SIGNING_KEY_VERSION' is not numeric" ;;
    *)             pass "SIGNING_KEY_VERSION is numeric ($SIGNING_KEY_VERSION)" ;;
  esac
fi

# RELEASE_SHA must identify this exact, clean checkout. This ensures the bytes
# sent by a manual `gcloud builds submit` match the image tag used as the
# immutable release identity.
if [ -n "${RELEASE_SHA:-}" ]; then
  case "$RELEASE_SHA" in
    *[!0-9a-f]*|"") fail "RELEASE_SHA must be exactly 40 lowercase hexadecimal characters" ;;
    *)
      if [ "${#RELEASE_SHA}" -ne 40 ]; then
        fail "RELEASE_SHA must be exactly 40 lowercase hexadecimal characters"
      else
        pass "RELEASE_SHA is a full lowercase Git SHA"
        if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
          HEAD_SHA=$(git rev-parse HEAD 2>/dev/null || true)
          [ "$HEAD_SHA" = "$RELEASE_SHA" ] \
            && pass "checkout HEAD matches RELEASE_SHA" \
            || fail "checkout HEAD ($HEAD_SHA) does not match RELEASE_SHA ($RELEASE_SHA)"
          if [ -z "$(git status --porcelain 2>/dev/null)" ]; then
            pass "checkout is clean"
          else
            fail "checkout is dirty; submitted bytes would not match RELEASE_SHA"
          fi
        else
          fail "git checkout unavailable; cannot prove submitted bytes match RELEASE_SHA"
        fi
      fi
      ;;
  esac
fi

echo
echo "=== Verdicts ==="
if [ "$SRC_FAIL" -gt 0 ]; then
  echo "SOURCE BLOCKED ($SRC_FAIL source check(s) failed)"
else
  echo "SOURCE READY"
fi
if [ "$ENV_FAIL" -gt 0 ]; then
  echo "DEPLOYMENT ENVIRONMENT BLOCKED ($ENV_FAIL item(s) missing)"
else
  echo "DEPLOYMENT ENVIRONMENT READY"
fi

[ "$SRC_FAIL" -gt 0 ] && exit 1
[ "$ENV_FAIL" -gt 0 ] && exit 2
exit 0
