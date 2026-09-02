#!/usr/bin/env bash
# Owner-only control for the Base44-to-coordinator connectivity switch. It is
# separate from public intake and is allowed to mutate exactly one setting.
set -euo pipefail

APP_ID="${BASE44_APP_ID:-6a498732ec779dfaaeab0e53}"
ACTION="${ACTION:-}"
SOURCE_SHA="${SOURCE_SHA:-}"
CONFIRM="${CONFIRM:-}"
BARRIER_EXPECTED_GENERATION="${BARRIER_EXPECTED_GENERATION:-}"
BASE44_EXPECTED_OWNER="${BASE44_EXPECTED_OWNER:-}"
CHANGE_TICKET="${CHANGE_TICKET:-}"
CUTOVER_REASON="${CUTOVER_REASON:-Base44 admission-connectivity control}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck source=scripts/lib/release-source-guard.sh
source "$REPO_ROOT/scripts/lib/release-source-guard.sh"
# shellcheck source=scripts/lib/base44-pinned-cli.sh
source "$REPO_ROOT/scripts/lib/base44-pinned-cli.sh"

fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$SOURCE_SHA"
SOURCE_SHA="$FIXLIST_EXACT_SOURCE_SHA"
if ! printf '%s' "$BARRIER_EXPECTED_GENERATION" | grep -Eq '^[0-9]+$'; then
  echo "Refusing Base44 admission-connectivity mutation: barrier generation must be numeric." >&2
  exit 2
fi

case "$ACTION" in
  disable)
    EXPECTED_CONFIRM="DISABLE-BASE44-ADMISSION-CONNECTIVITY:${SOURCE_SHA}:${BARRIER_EXPECTED_GENERATION}"
    VALUE=false
    ;;
  enable)
    EXPECTED_CONFIRM="ENABLE-BASE44-ADMISSION-CONNECTIVITY:${SOURCE_SHA}:${BARRIER_EXPECTED_GENERATION}"
    VALUE=true
    ;;
  *)
    echo "Refusing Base44 admission-connectivity mutation: ACTION must be disable or enable." >&2
    exit 2
    ;;
esac
if [[ "$CONFIRM" != "$EXPECTED_CONFIRM" ]]; then
  echo "Refusing Base44 admission-connectivity mutation: confirmation must be exactly '$EXPECTED_CONFIRM'." >&2
  exit 2
fi

# Connectivity changes are forbidden until the signed global barrier snapshot
# proves that claims are closed and every admission/reconciliation obligation
# has drained. The operator client reads only its isolated operator secret.
OPERATION=verify-zero-admission-obligations \
CONFIRM="VERIFY-ZERO-ADMISSION:${SOURCE_SHA}:${BARRIER_EXPECTED_GENERATION}" \
SOURCE_SHA="$SOURCE_SHA" \
BARRIER_EXPECTED_GENERATION="$BARRIER_EXPECTED_GENERATION" \
BARRIER_EXPECTED_PRIOR_MODE=closed \
CHANGE_TICKET="$CHANGE_TICKET" \
CUTOVER_REASON="$CUTOVER_REASON" \
  /bin/bash "$REPO_ROOT/scripts/fixlist-cloud-operator.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fixlist_install_base44_cli "$TMP"
# This control requires the protected self-hosted owner runner's existing CLI
# session. Never serialize or inject Base44 refresh tokens into Actions.
fixlist_require_base44_owner "$BASE44_EXPECTED_OWNER" "$TMP/whoami" "$APP_ID"

# This is the sole mutation. It never changes the public intake switch,
# coordinator URL, signing keys, checkout state, or any unrelated value.
"$FIXLIST_BASE44_CLI" --app-id "$APP_ID" secrets set \
  "BETA_SCAN_ADMISSION_ENABLED=$VALUE"

printf 'BASE44_ADMISSION_CONNECTIVITY_UPDATED\naction=%s\nsource_sha=%s\nbarrier_generation=%s\n' \
  "$ACTION" "$SOURCE_SHA" "$BARRIER_EXPECTED_GENERATION"
