#!/usr/bin/env bash
set -euo pipefail

PROJECT="seo-autopilot-501517"
REGION="europe-west1"
WORKER="fixlist-standard150-worker"
APP_ID="6a498732ec779dfaaeab0e53"

echo
echo "========== FIXLIST KEY SYNC =========="
echo "[1/6] Setting Google Cloud project..."
gcloud config set project "$PROJECT" >/dev/null
echo "OK — project set to $PROJECT"

TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

echo
echo "[2/6] Reading the signing-secret reference from the LIVE Python worker..."
gcloud run services describe "$WORKER" \
  --project="$PROJECT" \
  --region="$REGION" \
  --format=json > "$TMP/worker.json"

python3 - "$TMP/worker.json" "$TMP/ref.txt" <<'PY'
import json, sys

src, output = sys.argv[1], sys.argv[2]
with open(src, encoding="utf-8") as handle:
    data = json.load(handle)

containers = data.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
if not containers:
    raise SystemExit("ERROR: worker container configuration not found")

for item in containers[0].get("env", []):
    if item.get("name") != "SCAN_EVIDENCE_SIGNING_KEY":
        continue
    ref = item.get("valueFrom", {}).get("secretKeyRef", {})
    name = str(ref.get("name") or "").strip()
    version = str(ref.get("key") or "").strip()
    if not name or not version:
        raise SystemExit("ERROR: signing-secret reference is incomplete")
    if version == "latest" or not version.isdigit():
        raise SystemExit("ERROR: live worker signing secret is not pinned to a numeric version")
    with open(output, "w", encoding="utf-8") as handle:
        handle.write(f"{name} {version}\n")
    print(f"OK — live worker uses secret {name}, pinned version {version}")
    break
else:
    raise SystemExit("ERROR: live worker has no SCAN_EVIDENCE_SIGNING_KEY")
PY

read -r SIGNING_SECRET SIGNING_VERSION < "$TMP/ref.txt"

echo
echo "[3/6] Reading that exact pinned secret version from Secret Manager..."
echo "The secret VALUE will NOT be displayed."
gcloud secrets versions access "$SIGNING_VERSION" \
  --secret="$SIGNING_SECRET" \
  --project="$PROJECT" \
  > "$TMP/signing-key"
test -s "$TMP/signing-key"
echo "OK — canonical signing key retrieved securely"

echo
echo "[4/6] Preparing protected Base44 import file..."
{
  printf 'SCAN_EVIDENCE_SIGNING_KEY='
  cat "$TMP/signing-key"
  printf '\n'
} > "$TMP/base44.env"
chmod 600 "$TMP/signing-key" "$TMP/base44.env"
echo "OK — protected temporary import file created"

echo
echo "[5/6] Base44 login required"
echo "A DEVICE CODE SHOULD APPEAR BELOW."
echo "Open https://app.base44.com/login/device and approve it."
echo
npx -y base44@0.1.9 login

echo
echo "OK — Base44 authenticated"
echo
echo "[6/6] Synchronizing Base44 with the LIVE worker signing key..."
npx -y base44@0.1.9 \
  --app-id "$APP_ID" \
  secrets set --env-file "$TMP/base44.env"

echo
echo "======================================"
echo "KEY_SYNC_COMPLETE"
echo "======================================"
