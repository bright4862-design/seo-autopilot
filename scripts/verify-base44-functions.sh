#!/usr/bin/env bash
# Prove that every active Standard 150 Base44 scanner/customer route is executing
# the exact canonical package bytes from this source tree. Inventory membership and the site
# bundle are not enough: Base44 can report a function as "unchanged" while an
# older compiled handler continues serving.
set -euo pipefail

APP_ID="${BASE44_APP_ID:-6a498732ec779dfaaeab0e53}"
PROBE_ORIGIN="${BASE44_FUNCTION_ORIGIN:-https://base44.app}"
PROBE_ATTEMPTS="${PROBE_ATTEMPTS:-6}"
PROBE_DELAY_SECONDS="${PROBE_DELAY_SECONDS:-5}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

FUNCTION_PAIRS=(
  "startStandardScanJob:startStandardScanJobV2"
  "durableScanWorkerControl:durableScanWorkerControlV2"
  "persistDurableScanAuthority:persistDurableScanAuthorityV2"
  "persistLimitedScanResult:persistLimitedScanResultV2"
  "getCustomerScanResult:getCustomerScanResultV2"
  "deleteCustomerScanData:deleteCustomerScanDataV2"
)

command -v curl >/dev/null 2>&1 || {
  echo "Refusing Base44 function verification: curl is required." >&2
  exit 2
}
command -v node >/dev/null 2>&1 || {
  echo "Refusing Base44 function verification: node is required." >&2
  exit 2
}

if ! printf '%s' "$PROBE_ATTEMPTS" | grep -Eq '^[1-9][0-9]*$'; then
  echo "Refusing Base44 function verification: PROBE_ATTEMPTS must be a positive integer." >&2
  exit 2
fi
if ! printf '%s' "$PROBE_DELAY_SECONDS" | grep -Eq '^[0-9]+$'; then
  echo "Refusing Base44 function verification: PROBE_DELAY_SECONDS must be a non-negative integer." >&2
  exit 2
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

read_build_id() {
  local body_file="$1"
  node - "$body_file" <<'NODE'
const fs = require("node:fs");

const file = process.argv[2];
let value;
try {
  value = JSON.parse(fs.readFileSync(file, "utf8"));
} catch {
  process.exit(3);
}
const buildId = String(value?.build_id || "");
if (!/^[0-9a-f]{64}$/.test(buildId)) process.exit(4);
process.stdout.write(buildId);
NODE
}

for pair in "${FUNCTION_PAIRS[@]}"; do
  canonical="${pair%%:*}"
  name="${pair#*:}"
  expected="$(node "$REPO_ROOT/scripts/generate_release_contracts.mjs" --build-id "$canonical")"
  if ! printf '%s' "$expected" | grep -Eq '^[0-9a-f]{64}$'; then
    echo "Refusing Base44 function verification: local build ID for $name is invalid." >&2
    exit 2
  fi

  verified=""
  last_status="000"
  last_build_id=""
  attempt=1
  while (( attempt <= PROBE_ATTEMPTS )); do
    body="$TMP/${name}.json"
    status="$(curl -sS -o "$body" -w '%{http_code}' --max-time 25 \
      "$PROBE_ORIGIN/api/apps/$APP_ID/functions/$name" 2>/dev/null || echo 000)"
    actual="$(read_build_id "$body" 2>/dev/null || true)"
    last_status="$status"
    last_build_id="$actual"

    if [[ "$status" == "405" && "$actual" == "$expected" ]]; then
      printf 'FUNCTION_BUILD_VERIFIED name=%s build_id=%s\n' "$name" "$actual"
      verified="yes"
      break
    fi

    attempt=$(( attempt + 1 ))
    if (( attempt <= PROBE_ATTEMPTS )); then
      sleep "$PROBE_DELAY_SECONDS"
    fi
  done

  if [[ -z "$verified" ]]; then
    printf 'FUNCTION_BUILD_MISMATCH name=%s expected=%s actual=%s http_status=%s\n' \
      "$name" "$expected" "${last_build_id:-missing}" "$last_status" >&2
    exit 1
  fi
done

printf 'BASE44_FUNCTIONS_SOURCE_VERIFIED\n'
