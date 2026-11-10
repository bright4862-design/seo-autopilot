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
# only semantic difference is a missing comparison_evidence property. The write
# is the fetched ScanRun document plus that one approved property. Rollback
# deletes only that property from the fetched document. Every other byte comes
# from the live pre-image. A failed post-check, which requires the before and
# after documents to differ by that property alone, restores the pre-image.
#
# Rollback also reads ScanRun rows, requesting comparison_evidence on every
# page, and stops at the first stored value. A later page failure cannot turn
# that find into an unverified scan. A list that cannot be finished, and has
# not already found a stored value, does not count as proof: rollback then
# requires
# ROLLBACK-SCANRUN-COMPARISON-EVIDENCE-UNVERIFIED-ROWS:<sha>:<generation>.
# That override never applies when a stored value was actually returned.
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
    if [[ "$CONFIRM" != "$EXPECTED_CONFIRM" ]]; then
      echo "Refusing ScanRun schema migration: confirmation must be exactly '$EXPECTED_CONFIRM'." >&2
      exit 2
    fi
    ;;
  rollback)
    EXPECTED_CONFIRM="ROLLBACK-SCANRUN-COMPARISON-EVIDENCE:${SOURCE_SHA}:${BARRIER_EXPECTED_GENERATION}"
    UNVERIFIED_CONFIRM="ROLLBACK-SCANRUN-COMPARISON-EVIDENCE-UNVERIFIED-ROWS:${SOURCE_SHA}:${BARRIER_EXPECTED_GENERATION}"
    if [[ "$CONFIRM" != "$EXPECTED_CONFIRM" && "$CONFIRM" != "$UNVERIFIED_CONFIRM" ]]; then
      echo "Refusing ScanRun schema migration: confirmation must be exactly '$EXPECTED_CONFIRM'." >&2
      echo "If the row scan cannot be finished, the only other accepted confirmation is '$UNVERIFIED_CONFIRM'." >&2
      exit 2
    fi
    ;;
  *)
    echo "Refusing ScanRun schema migration: ACTION must be apply or rollback." >&2
    exit 2
    ;;
esac

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
node "$REPO_ROOT/scripts/base44_authority_schema.mjs" extract-scanrun "$TMP/before.json" "$TMP/preimage.json"

if [[ "$ACTION" == "rollback" ]]; then
  set +e
  node "$REPO_ROOT/scripts/base44_named_schema_client.mjs" evidence-rows > "$TMP/evidence.txt"
  evidence_status=$?
  set -e
  cat "$TMP/evidence.txt"
  if [[ "$evidence_status" -eq 0 ]]; then
    echo "SCANRUN_COMPARISON_EVIDENCE_ROWS_PROOF=clear"
  elif [[ "$evidence_status" -eq 3 ]]; then
    echo "Refusing rollback: a ScanRun row has stored comparison_evidence. The schema property stays." >&2
    exit 2
  elif [[ "$evidence_status" -eq 4 ]]; then
    if [[ "$CONFIRM" != "$UNVERIFIED_CONFIRM" ]]; then
      echo "Refusing rollback: the comparison_evidence row scan did not finish." >&2
      echo "Re-run only with confirmation '$UNVERIFIED_CONFIRM' if you accept that absence was not proven." >&2
      echo "That confirmation does not override a row the scan actually returned." >&2
      exit 2
    fi
    echo "SCANRUN_COMPARISON_EVIDENCE_ROWS_PROOF=unverified-override"
  else
    echo "Refusing rollback: the comparison_evidence row scan failed." >&2
    exit 2
  fi
fi

node "$REPO_ROOT/scripts/base44_authority_schema.mjs" write-live-mutation "$ACTION" "$TMP/preimage.json" "$TMP/next.json"
node "$REPO_ROOT/scripts/base44_named_schema_client.mjs" put "$TMP/next.json"
if ! node "$REPO_ROOT/scripts/base44_named_schema_client.mjs" fetch "$TMP/after.json" \
  || ! node "$REPO_ROOT/scripts/base44_authority_schema.mjs" extract-scanrun "$TMP/after.json" "$TMP/after-scan.json" \
  || ! node "$REPO_ROOT/scripts/base44_authority_schema.mjs" verify-live "$ACTION" "$TMP/preimage.json" "$TMP/after-scan.json" \
  || ! node "$REPO_ROOT/scripts/base44_authority_schema.mjs" verify-others "$TMP/after.json"; then
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
