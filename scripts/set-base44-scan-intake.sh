#!/usr/bin/env bash
# Owner-only control for the public Base44 scan-intake switch. This script
# intentionally cannot change coordinator connectivity or any other setting.
set -euo pipefail

APP_ID="${BASE44_APP_ID:-6a498732ec779dfaaeab0e53}"
ACTION="${ACTION:-}"
SOURCE_SHA="${SOURCE_SHA:-}"
CONFIRM="${CONFIRM:-}"
BASE44_EXPECTED_OWNER="${BASE44_EXPECTED_OWNER:-}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck source=scripts/lib/release-source-guard.sh
source "$REPO_ROOT/scripts/lib/release-source-guard.sh"
# shellcheck source=scripts/lib/base44-pinned-cli.sh
source "$REPO_ROOT/scripts/lib/base44-pinned-cli.sh"

fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$SOURCE_SHA"
SOURCE_SHA="$FIXLIST_EXACT_SOURCE_SHA"

case "$ACTION" in
  pause)
    EXPECTED_CONFIRM="PAUSE-BASE44-SCAN-INTAKE:${SOURCE_SHA}"
    VALUE=false
    ;;
  resume)
    EXPECTED_CONFIRM="RESUME-BASE44-SCAN-INTAKE:${SOURCE_SHA}"
    VALUE=true
    ;;
  *)
    echo "Refusing Base44 scan-intake mutation: ACTION must be pause or resume." >&2
    exit 2
    ;;
esac
if [[ "$CONFIRM" != "$EXPECTED_CONFIRM" ]]; then
  echo "Refusing Base44 scan-intake mutation: confirmation must be exactly '$EXPECTED_CONFIRM'." >&2
  exit 2
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fixlist_install_base44_cli "$TMP"
# Owner controls run only from a pre-authenticated owner workstation/runner.
# Device login is deliberately not attempted here: it cannot be completed
# safely or non-interactively by a hosted GitHub runner.
fixlist_require_base44_owner "$BASE44_EXPECTED_OWNER" "$TMP/whoami" "$APP_ID"

# This is the sole mutation. In particular, do not list, delete, export, or
# replace admission-connectivity or unrelated Base44 values.
"$FIXLIST_BASE44_CLI" --app-id "$APP_ID" secrets set \
  "BETA_SCAN_INTAKE_ENABLED=$VALUE"

# A zero exit from `secrets set` is not sufficient release evidence. Verify
# the published customer function observes the requested value before claiming
# the control succeeded. The verifier uses a nonexistent project so it cannot
# create a ScanRun, claim admission, or enqueue a task.
FIXLIST_BASE44_CLI="$FIXLIST_BASE44_CLI" \
BASE44_APP_ID="$APP_ID" \
ACTION="$ACTION" \
/bin/bash "$REPO_ROOT/scripts/verify-base44-scan-intake-runtime.sh"

printf 'BASE44_SCAN_INTAKE_UPDATED\naction=%s\nsource_sha=%s\n' "$ACTION" "$SOURCE_SHA"
