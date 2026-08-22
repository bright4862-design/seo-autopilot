#!/usr/bin/env bash
# Install Base44 CLI from a pinned tarball and verify npm's published SRI digest.
set -euo pipefail

FIXLIST_BASE44_CLI_VERSION="0.1.8"
FIXLIST_BASE44_CLI_SHA512="sha512-Vquv/Jdzj+XECE2YEtU/oFQVCawqJDAvnsgl9fBEXHpg0gtBiYE/roImzujYiR1zX2Yy9a7XqUMysIDDAIuo2g=="

fixlist_install_base44_cli() {
  local root="$1"
  mkdir -p "$root"
  chmod 700 "$root"
  npm pack "base44@${FIXLIST_BASE44_CLI_VERSION}" --pack-destination "$root" >/dev/null
  local tgz="$root/base44-${FIXLIST_BASE44_CLI_VERSION}.tgz"
  test -s "$tgz"
  local got
  got="sha512-$(openssl dgst -sha512 -binary "$tgz" | openssl base64 -A)"
  if [[ "$got" != "$FIXLIST_BASE44_CLI_SHA512" ]]; then
    echo "Refusing: base44@${FIXLIST_BASE44_CLI_VERSION} tarball integrity mismatch." >&2
    return 2
  fi
  npm install --prefix "$root/cli" --no-save --save-exact --ignore-scripts "$tgz" >/dev/null
  FIXLIST_BASE44_CLI="$root/cli/node_modules/.bin/base44"
  test -x "$FIXLIST_BASE44_CLI"
  export FIXLIST_BASE44_CLI
  printf 'base44_cli=verified@%s\n' "$FIXLIST_BASE44_CLI_VERSION"
}

# Base44 mutations are owner-only. Keep the CLI's identity response in a
# protected temporary file so a failed identity check cannot disclose account
# details in Actions logs.
fixlist_require_base44_owner() {
  local expected_owner="$1" output="$2"
  if [[ -z "$expected_owner" || ${#expected_owner} -gt 200 || "$expected_owner" == *$'\n'* ]]; then
    echo "Refusing Base44 mutation: BASE44_EXPECTED_OWNER is missing or invalid." >&2
    return 2
  fi
  umask 077
  : > "$output"
  chmod 600 "$output"
  if ! "$FIXLIST_BASE44_CLI" whoami > "$output" 2>&1; then
    echo "Refusing Base44 mutation: authenticated identity could not be verified." >&2
    return 2
  fi
  if ! EXPECTED_BASE44_OWNER="$expected_owner" python3 - "$output" <<'PY'
import os, sys

expected = os.environ["EXPECTED_BASE44_OWNER"]
lines = [line.strip() for line in open(sys.argv[1], encoding="utf-8", errors="replace")]
if f"Logged in as: {expected}" not in lines:
    raise SystemExit(1)
PY
  then
    echo "Refusing Base44 mutation: authenticated identity is not the configured owner." >&2
    return 2
  fi
  printf 'base44_owner=verified\n'
}

fixlist_set_base44_release_source_sha() {
  local app_id="$1" source_sha="$2"
  if ! printf '%s' "$source_sha" | grep -Eq '^[0-9a-f]{40}$'; then
    echo "Refusing Base44 provenance update: source SHA is invalid." >&2
    return 2
  fi
  "$FIXLIST_BASE44_CLI" --app-id "$app_id" secrets set \
    "FIXLIST_RELEASE_SOURCE_SHA=$source_sha"
  printf 'base44_release_source_sha=verified\n'
}
