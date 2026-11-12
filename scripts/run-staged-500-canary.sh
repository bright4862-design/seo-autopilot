#!/usr/bin/env bash
# Exactly one explicitly authorized request against an existing 500 entitlement.
# No project, grant, cohort, deployment or infrastructure mutation is performed.
set -euo pipefail
umask 077
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ID="${BASE44_APP_ID:-6a498732ec779dfaaeab0e53}"
SOURCE_SHA="${SOURCE_SHA:-}"
EXPECTED_OWNER_USER_ID="${EXPECTED_OWNER_USER_ID:-}"
PROJECT_ID="${PROJECT_ID:-}"
REQUEST_ID="${REQUEST_ID:-}"
TARGET_URL="${TARGET_URL:-}"
PREREQUISITES_FILE="${PREREQUISITES_FILE:-}"
ACCEPTANCE_OUTPUT="${ACCEPTANCE_OUTPUT:-}"
MAX_WAIT_SECONDS="${MAX_WAIT_SECONDS:-900}"
POLL_SECONDS="${POLL_SECONDS:-5}"
EXPECTED_CONFIRM="RUN-ONE-STAGED-500-CANARY:${SOURCE_SHA}:${EXPECTED_OWNER_USER_ID}:${PROJECT_ID}:${REQUEST_ID}"
if [[ "$APP_ID" != 6a498732ec779dfaaeab0e53 || ! "$SOURCE_SHA" =~ ^[a-f0-9]{40}$ || ! "$EXPECTED_OWNER_USER_ID" =~ ^[A-Za-z0-9_-]{6,160}$ || ! "$PROJECT_ID" =~ ^[A-Za-z0-9_-]{6,160}$ || ! "$REQUEST_ID" =~ ^[A-Za-z0-9_-]{8,160}$ || "${CONFIRM:-}" != "$EXPECTED_CONFIRM" ]]; then
  echo 'Refusing: exact source, owner, existing project, stable request and RUN-ONE-STAGED-500-CANARY confirmation required.' >&2
  exit 2
fi
if [[ ! "$MAX_WAIT_SECONDS" =~ ^[0-9]+$ || ! "$POLL_SECONDS" =~ ^[0-9]+$ ]] || (( MAX_WAIT_SECONDS < 1 || MAX_WAIT_SECONDS > 1800 || POLL_SECONDS < 1 || POLL_SECONDS > 60 )); then
  echo 'Refusing: bounded MAX_WAIT_SECONDS=1..1800 and POLL_SECONDS=1..60 required.' >&2; exit 2
fi
if [[ "$PREREQUISITES_FILE" != /* || ! -f "$PREREQUISITES_FILE" || -L "$PREREQUISITES_FILE" || "$ACCEPTANCE_OUTPUT" != /* || -e "$ACCEPTANCE_OUTPUT" || -L "$ACCEPTANCE_OUTPUT" ]]; then
  echo 'Refusing: an existing absolute prerequisite file and new absolute acceptance output are required.' >&2; exit 2
fi
for executable in node deno timeout; do command -v "$executable" >/dev/null 2>&1 || { echo "Refusing: $executable required." >&2; exit 2; }; done
export SOURCE_SHA EXPECTED_OWNER_USER_ID PROJECT_ID REQUEST_ID TARGET_URL PREREQUISITES_FILE MAX_WAIT_SECONDS POLL_SECONDS
node --input-type=module - "$REPO_ROOT" "$ACCEPTANCE_OUTPUT" <<'NODE'
import fs from 'node:fs';
import path from 'node:path';
const [root, output] = process.argv.slice(2), parent = path.dirname(output);
if (!fs.existsSync(parent) || fs.realpathSync(parent) !== parent) throw new Error('Acceptance parent must exist without symlink aliases');
const relative = path.relative(fs.realpathSync(root), parent);
if (!relative || (relative !== '..' && !relative.startsWith('..' + path.sep))) throw new Error('Acceptance output must be outside source checkout');
if (fs.existsSync(output)) throw new Error('Prior evidence must never be overwritten');
NODE
source "$REPO_ROOT/scripts/lib/release-source-guard.sh"
source "$REPO_ROOT/scripts/lib/base44-pinned-cli.sh"
fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$SOURCE_SHA"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
# Validate every prerequisite before installing the CLI or submitting the scan.
node "$REPO_ROOT/scripts/staged_scan_acceptance.mjs" render > "$TMP/payload.js"
fixlist_install_base44_cli "$TMP/cli"
set +e
timeout --signal=TERM "$((MAX_WAIT_SECONDS + 120))" "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" exec --data-env prod < "$TMP/payload.js" > "$TMP/output" 2> "$TMP/error"
CLI_STATUS=$?
set -e
# Raw SDK output/errors may contain private evidence. Only the filtered report
# produced by our payload is persisted or printed.
node "$REPO_ROOT/scripts/staged_scan_acceptance.mjs" collect "$TMP/output" "$ACCEPTANCE_OUTPUT" "$CLI_STATUS"
