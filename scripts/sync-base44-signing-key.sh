#!/usr/bin/env bash
set -euo pipefail

PROJECT="seo-autopilot-501517"
REGION="europe-west1"
WORKER="fixlist-standard150-worker"
APP_ID="6a498732ec779dfaaeab0e53"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# The Base44 CLI handles the plaintext signing key, so it is pinned by version
# AND verified by tarball digest before it is installed. `npx -y pkg@ver` would
# resolve and execute whatever the registry serves at run time.
BASE44_CLI_VERSION="0.1.9"
# npm SRI form, as published for base44@0.1.9. Independently verified against
# the registry by the release owner. Either form is accepted below: the
# "sha512-" prefix is what npm and the registry actually show, so rejecting it
# would make the natural copy-paste fail closed for the wrong reason.
BASE44_CLI_SHA512="${BASE44_CLI_SHA512:-sha512-o1IFePlQHvUARUVr19FiYEakkPrwDf6IVcz3pWSngSaG+sBSs8t7T7coJir1N4yBFQ76052hjgqT2V+xC8BNOQ==}"

echo
echo "========== FIXLIST KEY SYNC =========="
echo "[1/8] Setting Google Cloud project..."
gcloud config set project "$PROJECT" >/dev/null
echo "OK — project set to $PROJECT"

TMP="$(mktemp -d)"
chmod 700 "$TMP"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

echo
echo "[2/8] Reading the signing-secret reference from the LIVE Python worker..."
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
echo "[3/8] Installing and verifying the pinned Base44 CLI..."
npm pack "base44@${BASE44_CLI_VERSION}" --pack-destination "$TMP" >/dev/null
TGZ="$TMP/base44-${BASE44_CLI_VERSION}.tgz"
test -s "$TGZ"
# openssl emits the bare base64 digest; npm publishes it as "sha512-<base64>".
# Normalize both sides so an operator can paste either form. A pinned value that
# silently never matches its own artifact is a fail-closed check that fails for
# the wrong reason, which is indistinguishable from a real supply-chain hit.
GOT_SHA512="sha512-$(openssl dgst -sha512 -binary "$TGZ" | openssl base64 -A)"
EXPECTED_SHA512="$BASE44_CLI_SHA512"
case "$EXPECTED_SHA512" in
  sha512-*) ;;
  "")       ;;
  *)        EXPECTED_SHA512="sha512-${EXPECTED_SHA512}" ;;
esac

if [ -n "$EXPECTED_SHA512" ]; then
  if [ "$GOT_SHA512" != "$EXPECTED_SHA512" ]; then
    echo "ERROR: base44@${BASE44_CLI_VERSION} integrity mismatch" >&2
    echo "  expected: $EXPECTED_SHA512" >&2
    echo "  got:      $GOT_SHA512" >&2
    exit 1
  fi
  echo "OK — CLI tarball digest matches the pinned value"
else
  echo "ERROR: BASE44_CLI_SHA512 is not set." >&2
  echo "This script will not hand the signing key to an unverified CLI build." >&2
  echo "Observed digest for base44@${BASE44_CLI_VERSION}:" >&2
  echo "  $GOT_SHA512" >&2
  echo "Verify it against the registry, then re-run with BASE44_CLI_SHA512 set." >&2
  exit 1
fi
npm install --prefix "$TMP/cli" --no-save --save-exact --ignore-scripts "$TGZ" >/dev/null
CLI="$TMP/cli/node_modules/.bin/base44"
test -x "$CLI"
echo "OK — base44@${BASE44_CLI_VERSION} installed from the verified tarball"

echo
echo "[4/8] Base44 login required — BEFORE any secret is read"
echo "A DEVICE CODE SHOULD APPEAR BELOW."
echo "Open https://app.base44.com/login/device and approve it."
echo
"$CLI" login
echo
echo "OK — Base44 authenticated"

echo
echo "[5/8] Reading that exact pinned secret version from Secret Manager..."
echo "The secret VALUE will NOT be displayed."
gcloud secrets versions access "$SIGNING_VERSION" \
  --secret="$SIGNING_SECRET" \
  --project="$PROJECT" \
  > "$TMP/signing-key"
test -s "$TMP/signing-key"
echo "OK — canonical signing key retrieved securely"

echo
echo "[6/8] Encoding the exact signing-key bytes for Base44..."
# Cloud Run injects a secret payload verbatim, so the worker and the coordinator
# both sign with whatever bytes the version holds, trailing newline included.
# The pinned Base44 CLI's dotenv parser preserves literal bytes inside quoted,
# multiline values. Use that form so Base44 receives the canonical root exactly,
# rather than the stripped value produced by the former unquoted env entry.
python3 "$REPO_ROOT/scripts/encode-base44-signing-key-env.py" \
  "$TMP/signing-key" \
  "$TMP/base44.env"
chmod 600 "$TMP/signing-key" "$TMP/base44.env"
echo "OK — protected temporary import file created"

echo
echo "[7/8] Verifying protected Base44 import byte identity..."
python3 - "$TMP/signing-key" "$TMP/base44.env" <<'VERIFY'
import hmac
import sys

payload = open(sys.argv[1], "rb").read()
encoded = open(sys.argv[2], "rb").read()
prefix = b"SCAN_EVIDENCE_SIGNING_KEY="

if not encoded.startswith(prefix) or not encoded.endswith(b"\n"):
    raise SystemExit("ERROR: protected Base44 import has an invalid envelope")
quoted = encoded[len(prefix):-1]
if len(quoted) < 2 or quoted[:1] not in (b"'", b"`") or quoted[-1:] != quoted[:1]:
    raise SystemExit("ERROR: protected Base44 import has an invalid delimiter")
if not hmac.compare_digest(payload, quoted[1:-1]):
    raise SystemExit("ERROR: protected Base44 import changed the signing-key bytes")
print("OK — Base44 import contains the canonical signing-key bytes exactly")
VERIFY

echo
echo "[8/8] Synchronizing Base44 with the LIVE worker signing key..."
"$CLI" --app-id "$APP_ID" secrets set --env-file "$TMP/base44.env"

echo
echo "======================================"
echo "KEY_SYNC_COMPLETE"
echo "======================================"
