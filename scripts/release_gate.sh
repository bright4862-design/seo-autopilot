#!/usr/bin/env bash
# One complete release gate for the durable Standard 150 candidate.
#
# Runs every available check and reports TWO INDEPENDENT verdicts, so a missing
# local tool can never disguise whether the repository source is green:
#
#   SOURCE READY | SOURCE BLOCKED
#   DEPLOYMENT ENVIRONMENT READY | DEPLOYMENT ENVIRONMENT BLOCKED
#
# Read-only: no deploy, no GCP call, no Base44 call, no network mutation.
#
# Exit 0 = source ready and environment ready
#      1 = source blocked
#      2 = source ready, environment blocked
#
# Usage:  bash scripts/release_gate.sh
#         PYTHON=/path/to/venv/bin/python bash scripts/release_gate.sh

set -uo pipefail

PYTHON="${PYTHON:-python3}"
SRC_FAIL=0
RESULTS=()

step() {
  local label="$1"; shift
  local out status
  out=$("$@" 2>&1); status=$?
  if [ "$status" -eq 0 ]; then
    RESULTS+=("PASS  $label")
    printf "PASS  %s\n" "$label"
  else
    RESULTS+=("FAIL  $label")
    printf "FAIL  %s\n" "$label"
    printf "%s\n" "$out" | tail -15 | sed 's/^/        /'
    SRC_FAIL=$((SRC_FAIL + 1))
  fi
}

echo "########## SOURCE GATES ##########"
step "lint"                        npm run lint --silent
step "typecheck"                   npm run typecheck --silent
step "frontend contract tests"     npm run test:frontend --silent
step "production build"            npm run build
step "base44 package integrity"    node scripts/base44_release_manifest.mjs verify
step "root python tests"           "$PYTHON" -m pytest tests/ -q
step "scanner api tests"           bash -c "cd scanner-api && '$PYTHON' -m pytest tests/ -q"
step "frozen beta revision"        bash -c "cd scanner-api && '$PYTHON' scripts/freeze_beta_revision.py --check"

# Manifest determinism: two independent runs must be byte-identical.
step "release manifest determinism" bash -c '
  a=$(node scripts/base44_release_manifest.mjs manifest)
  b=$(node scripts/base44_release_manifest.mjs manifest)
  [ "$a" = "$b" ]'

echo
echo "########## DEPLOYMENT PREFLIGHT ##########"
# Preflight owns the environment verdict. Exit 1 means a real source defect.
preflight_out=$(bash scripts/deployment_preflight.sh 2>&1)
preflight_status=$?
printf "%s\n" "$preflight_out"
if [ "$preflight_status" -eq 1 ]; then
  SRC_FAIL=$((SRC_FAIL + 1))
fi
ENV_BLOCKED=0
[ "$preflight_status" -eq 2 ] && ENV_BLOCKED=1

echo
echo "########## RELEASE MANIFEST ##########"
node scripts/base44_release_manifest.mjs manifest \
  | "$PYTHON" -c "
import sys, json
d = json.load(sys.stdin)
for name, fn in d['functions'].items():
    print(f\"{name}  entry={fn['entry']}  package={fn['packageDigest']}\")
print('release_digest:', d['releaseDigest'])
" 2>/dev/null || echo "(manifest unavailable)"

echo
echo "########## VERDICTS ##########"
for r in "${RESULTS[@]}"; do printf "  %s\n" "$r"; done
echo
if [ "$SRC_FAIL" -gt 0 ]; then
  echo "SOURCE BLOCKED ($SRC_FAIL gate(s) failed)"
else
  echo "SOURCE READY"
fi
if [ "$ENV_BLOCKED" -eq 1 ]; then
  echo "DEPLOYMENT ENVIRONMENT BLOCKED"
else
  echo "DEPLOYMENT ENVIRONMENT READY"
fi

[ "$SRC_FAIL" -gt 0 ] && exit 1
[ "$ENV_BLOCKED" -eq 1 ] && exit 2
exit 0
