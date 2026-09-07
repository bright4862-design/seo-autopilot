#!/usr/bin/env bash
# Prove that every active Standard 150 Base44 scanner/customer route is executing
# the exact canonical package bytes from this source tree. Inventory membership and the site
# bundle are not enough: Base44 can report a function as "unchanged" while an
# older compiled handler continues serving.
set -euo pipefail

APP_ID="${BASE44_APP_ID:-6a498732ec779dfaaeab0e53}"
PROBE_ORIGIN="${BASE44_FUNCTION_ORIGIN:-https://base44.app}"
# A route that has never been compiled under this name can take longer to
# activate than one Base44 has served before, and the probe is fail-closed:
# waiting longer can only avoid a false NO-GO, never manufacture a pass. The
# loop exits on the first mismatch, so the worst case is one function.
PROBE_ATTEMPTS="${PROBE_ATTEMPTS:-12}"
PROBE_DELAY_SECONDS="${PROBE_DELAY_SECONDS:-5}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# The live routes. Each one's expected build ID is resolved through the alias
# table by the generator, so this list no longer carries the canonical name.
FUNCTION_ROUTES=(
  startStandardScanJobV2
  durableScanWorkerControlV2
  persistDurableScanAuthorityV2
  persistLimitedScanResultV2
  getCustomerScanResultV2
  deleteCustomerScanDataV2
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

read_runtime_identity() {
  # Both markers, or nothing. A handler that answers with only one of them is
  # not a handler this verification can vouch for.
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
if (value === null || typeof value !== "object" || Array.isArray(value)) process.exit(3);
const buildId = String(value?.build_id || "");
if (!/^[0-9a-f]{64}$/.test(buildId)) process.exit(4);
const activationId = String(value?.runtime_activation_id || "");
if (!/^[A-Za-z0-9._-]{1,120}$/.test(activationId)) process.exit(5);
process.stdout.write(`${buildId} ${activationId}`);
NODE
}

for name in "${FUNCTION_ROUTES[@]}"; do
  # The build ID resolves through the alias, because an alias is stamped with
  # the identity of the package it mirrors. The activation marker does not:
  # each package carries its own. That asymmetry is the whole point of checking
  # both -- deleteCustomerScanDataV2's canonical package was unchanged by the
  # activation refresh, so its expected build ID still equals the one the stale
  # handler serves, and a build-only check calls that route current while it is
  # running canonical-era code.
  expected="$(node "$REPO_ROOT/scripts/generate_release_contracts.mjs" --build-id "$name")"
  if ! printf '%s' "$expected" | grep -Eq '^[0-9a-f]{64}$'; then
    echo "Refusing Base44 function verification: local build ID for $name is invalid." >&2
    exit 2
  fi
  expected_activation="$(node "$REPO_ROOT/scripts/generate_release_contracts.mjs" --activation-id "$name")"
  if ! printf '%s' "$expected_activation" | grep -Eq '^[A-Za-z0-9._-]{1,120}$'; then
    echo "Refusing Base44 function verification: local activation marker for $name is invalid." >&2
    exit 2
  fi

  verified=""
  last_status="000"
  last_build_id=""
  last_activation_id=""
  attempt=1
  while (( attempt <= PROBE_ATTEMPTS )); do
    body="$TMP/${name}.json"
    status="$(curl -sS -o "$body" -w '%{http_code}' --max-time 25 \
      "$PROBE_ORIGIN/api/apps/$APP_ID/functions/$name" 2>/dev/null || echo 000)"
    identity="$(read_runtime_identity "$body" 2>/dev/null || true)"
    actual="${identity%% *}"
    actual_activation=""
    [[ "$identity" == *" "* ]] && actual_activation="${identity#* }"
    last_status="$status"
    last_build_id="$actual"
    last_activation_id="$actual_activation"

    if [[ "$status" == "405" && "$actual" == "$expected" && "$actual_activation" == "$expected_activation" ]]; then
      printf 'FUNCTION_RUNTIME_VERIFIED name=%s build_id=%s runtime_activation_id=%s\n' \
        "$name" "$actual" "$actual_activation"
      verified="yes"
      break
    fi

    attempt=$(( attempt + 1 ))
    if (( attempt <= PROBE_ATTEMPTS )); then
      sleep "$PROBE_DELAY_SECONDS"
    fi
  done

  if [[ -z "$verified" ]]; then
    printf 'FUNCTION_BUILD_MISMATCH name=%s expected=%s actual=%s expected_activation=%s actual_activation=%s http_status=%s\n' \
      "$name" "$expected" "${last_build_id:-missing}" "$expected_activation" \
      "${last_activation_id:-missing}" "$last_status" >&2
    exit 1
  fi
done

printf 'BASE44_FUNCTIONS_SOURCE_VERIFIED\n'
