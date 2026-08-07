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
  has "--timeout=300" "$WORKER_BUILD" \
    && pass "Cloud Run timeout 300s" || fail "Cloud Run timeout is not 300s"
  has "--concurrency=1" "$WORKER_BUILD" \
    && pass "concurrency 1" || fail "concurrency is not 1"
  has "--no-traffic" "$WORKER_BUILD" \
    && pass "no traffic migration on deploy" || fail "deploy would migrate traffic"
  has "GROK_CHAT_ENABLED=false" "$WORKER_BUILD" \
    && pass "Grok disabled in worker env" || fail "Grok not explicitly disabled"
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
  has 'dispatchDeadline: "300s"' "$TASKS" && pass "dispatchDeadline 300s" || fail "dispatchDeadline not 300s"
  has "oidcToken" "$TASKS" && pass "task carries OIDC token" || fail "task has no OIDC token"
  has "serviceAccountEmail" "$TASKS" && pass "OIDC invoker SA set" || fail "OIDC has no invoker SA"
  has "audience" "$TASKS" && pass "OIDC audience set" || fail "OIDC has no audience"
  has 'standard150-${safeId}-a${attempt}' "$TASKS" \
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
for var in WORKER_SERVICE REGION IMAGE RUNTIME_SA INVOKER_SA TASKS_QUEUE; do
  if [ -n "${!var:-}" ]; then pass "$var supplied"; else envm "$var not supplied"; fi
done

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
