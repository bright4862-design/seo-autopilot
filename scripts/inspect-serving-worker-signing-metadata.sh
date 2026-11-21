#!/usr/bin/env bash
# Read-only rehearsal for Standard 150 serving-revision signing-ref metadata.
# NEVER reads a signing secret, imports Base44 secrets, or changes Cloud Run.
# Metadata agreement is NOT proof of signing-byte continuity or a release GO.
set -euo pipefail

: "${GCP_PROJECT:?GCP_PROJECT is required}"
: "${GCP_REGION:?GCP_REGION is required}"
: "${CLOUD_RUN_SERVICE:?CLOUD_RUN_SERVICE is required}"

# This tool certifies only the production Standard 150 namespace. Reading a
# similarly named revision from another project/region/service must not be
# confused with evidence for this customer path.
if [[ "$GCP_PROJECT" != "seo-autopilot-501517" ||
      "$GCP_REGION" != "europe-west1" ||
      "$CLOUD_RUN_SERVICE" != "fixlist-standard150-worker" ]]; then
  echo "ERROR: production scope mismatch; expected seo-autopilot-501517/europe-west1/fixlist-standard150-worker" >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GUARD="$REPO_ROOT/scripts/select-serving-worker-signing-ref.py"
test -f "$GUARD"
TMP="$(mktemp -d)"
chmod 700 "$TMP"
trap 'rm -rf "$TMP"' EXIT

observe() {
  # No 'gcloud config set' or other operation with side effects.
  gcloud run services describe "$CLOUD_RUN_SERVICE" \
    --project="$GCP_PROJECT" --region="$GCP_REGION" --format=json > "$TMP/service.json"
  # A successful lookup must describe exactly the requested service.
  python3 - "$TMP/service.json" "$CLOUD_RUN_SERVICE" <<'PY'
import json
import sys
service = json.load(open(sys.argv[1], encoding="utf-8"))
if (service.get("metadata") or {}).get("name") != sys.argv[2]:
    raise SystemExit("ERROR: described Cloud Run service name differs from requested service")
PY
  local revision
  revision="$(python3 "$GUARD" revision-name "$TMP/service.json")"
  gcloud run revisions describe "$revision" \
    --project="$GCP_PROJECT" --region="$GCP_REGION" --format=json > "$TMP/revision.json"
}

observe
# Suppress the guard's metadata summary, which includes the secret's NAME and
# numeric version. The temporary receipt is not uploaded or printed.
python3 "$GUARD" select "$TMP/service.json" "$TMP/revision.json" "$TMP/ref.txt" > /dev/null
revision="$(sed -n '2p' "$TMP/ref.txt")"
test -n "$revision"

# Re-observe the whole service+revision pair, not just the selected secret ref.
# Even a same-key traffic move must reject the original receipt.
observe
python3 "$GUARD" verify "$TMP/service.json" "$TMP/revision.json" "$TMP/ref.txt" > /dev/null

printf 'KEYLESS_METADATA_PREFLIGHT_OK project=%s region=%s service=%s revision=%s\n' \
  "$GCP_PROJECT" "$GCP_REGION" "$CLOUD_RUN_SERVICE" "$revision"
echo "This confirms two agreeing metadata observations only."
echo "It does NOT prove the deployed /revision payload, signing-key bytes,"
echo "historical HMAC read-back, Base44 package identity, or release acceptance."
