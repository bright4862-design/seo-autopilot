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
