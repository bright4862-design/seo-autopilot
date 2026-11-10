#!/usr/bin/env bash
# Closed-barrier migration for the one approved ScanRun property.
#
# The deployment contract forbids a bulk entity sync: that command replaces
# every entity and deletes remote entities that are absent locally. This path
# instead reuses the admission-connectivity gate (exact main, owner session,
# closed and drained barrier) and then replaces only the ScanRun schema
# through the named entity-schema API.
#
# Apply is allowed only when FixList and FixItem already match and ScanRun's
# only difference is a missing comparison_evidence property. Rollback puts the
# same local schema with that one property removed, and only when the live
# schema otherwise matches. A failed post-check restores the schema fetched
# before the write.
set -euo pipefail

APP_ID="${BASE44_APP_ID:-6a498732ec779dfaaeab0e53}"
ACTION="${ACTION:-}"
SOURCE_SHA="${SOURCE_SHA:-}"
CONFIRM="${CONFIRM:-}"
BARRIER_EXPECTED_GENERATION="${BARRIER_EXPECTED_GENERATION:-}"
BASE44_EXPECTED_OWNER="${BASE44_EXPECTED_OWNER:-}"
CHANGE_TICKET="${CHANGE_TICKET:-}"
CUTOVER_REASON="${CUTOVER_REASON:-ScanRun comparison_evidence schema migration}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck source=scripts/lib/release-source-guard.sh
source "$REPO_ROOT/scripts/lib/release-source-guard.sh"
# shellcheck source=scripts/lib/base44-pinned-cli.sh
source "$REPO_ROOT/scripts/lib/base44-pinned-cli.sh"

fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$SOURCE_SHA"
SOURCE_SHA="$FIXLIST_EXACT_SOURCE_SHA"
if ! printf '%s' "$BARRIER_EXPECTED_GENERATION" | grep -Eq '^[0-9]+$'; then
  echo "Refusing ScanRun schema migration: barrier generation must be numeric." >&2
  exit 2
fi
if [[ "${BARRIER_EXPECTED_PRIOR_MODE:-closed}" != "closed" ]]; then
  echo "Refusing ScanRun schema migration: barrier prior mode must be closed." >&2
  exit 2
fi

case "$ACTION" in
  apply)
    EXPECTED_CONFIRM="APPLY-SCANRUN-COMPARISON-EVIDENCE:${SOURCE_SHA}:${BARRIER_EXPECTED_GENERATION}"
    ;;
  rollback)
    EXPECTED_CONFIRM="ROLLBACK-SCANRUN-COMPARISON-EVIDENCE:${SOURCE_SHA}:${BARRIER_EXPECTED_GENERATION}"
    ;;
  *)
    echo "Refusing ScanRun schema migration: ACTION must be apply or rollback." >&2
    exit 2
    ;;
esac
if [[ "$CONFIRM" != "$EXPECTED_CONFIRM" ]]; then
  echo "Refusing ScanRun schema migration: confirmation must be exactly '$EXPECTED_CONFIRM'." >&2
  exit 2
fi

# Prove the barrier before any Base44 session or schema write. The nested
# operator reads only its own signing secret and does not pause queues.
OPERATION=verify-zero-admission-obligations \
CONFIRM="VERIFY-ZERO-ADMISSION:${SOURCE_SHA}:${BARRIER_EXPECTED_GENERATION}" \
SOURCE_SHA="$SOURCE_SHA" \
BARRIER_EXPECTED_GENERATION="$BARRIER_EXPECTED_GENERATION" \
BARRIER_EXPECTED_PRIOR_MODE=closed \
CHANGE_TICKET="$CHANGE_TICKET" \
CUTOVER_REASON="$CUTOVER_REASON" \
GCP_OPERATOR_SERVICE_ACCOUNT="${GCP_ADMISSION_OPERATOR_SERVICE_ACCOUNT:-${GCP_OPERATOR_SERVICE_ACCOUNT:-}}" \
  /bin/bash "$REPO_ROOT/scripts/fixlist-cloud-operator.sh"

TMP="$(mktemp -d)"
chmod 700 "$TMP"
trap 'rm -rf "$TMP"' EXIT
fixlist_install_base44_cli "$TMP"
fixlist_require_base44_owner "$BASE44_EXPECTED_OWNER" "$TMP/whoami" "$APP_ID"

node "$REPO_ROOT/scripts/base44_named_schema_client.mjs" fetch "$TMP/before.json"
node "$REPO_ROOT/scripts/base44_authority_schema.mjs" decide "$TMP/before.json" "$ACTION"
node "$REPO_ROOT/scripts/base44_authority_schema.mjs" write-schema "$ACTION" "$TMP/next.json"
node "$REPO_ROOT/scripts/base44_authority_schema.mjs" extract-scanrun "$TMP/before.json" "$TMP/preimage.json"

node "$REPO_ROOT/scripts/base44_named_schema_client.mjs" put "$TMP/next.json"
if ! node "$REPO_ROOT/scripts/base44_named_schema_client.mjs" fetch "$TMP/after.json" \
  || ! node "$REPO_ROOT/scripts/base44_authority_schema.mjs" verify "$TMP/after.json" "$ACTION"; then
  echo "SCHEMA_MIGRATION_VERIFY_FAILED restoring the pre-write ScanRun schema" >&2
  if node "$REPO_ROOT/scripts/base44_named_schema_client.mjs" put "$TMP/preimage.json"; then
    echo "SCHEMA_MIGRATION_PREIMAGE_RESTORED entity=ScanRun" >&2
  else
    echo "SCHEMA_MIGRATION_ROLLBACK_FAILED entity=ScanRun" >&2
  fi
  exit 1
fi

printf 'SCANRUN_COMPARISON_EVIDENCE_%s\nsource_sha=%s\nbarrier_generation=%s\n' \
  "$(printf '%s' "$ACTION" | tr '[:lower:]' '[:upper:]')" \
  "$SOURCE_SHA" \
  "$BARRIER_EXPECTED_GENERATION"
