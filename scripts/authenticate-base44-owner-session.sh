#!/usr/bin/env bash
# Authenticate an ephemeral hosted runner as the configured Base44 owner.
#
# This is the Builder-compatible counterpart to workspace-key auth. The CLI
# device session exists only for the lifetime of the hosted runner; no refresh
# token or access token is serialized into GitHub secrets or repository files.
set -euo pipefail

APP_ID="${BASE44_APP_ID:-6a498732ec779dfaaeab0e53}"
BASE44_EXPECTED_OWNER="${BASE44_EXPECTED_OWNER:-}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO_ROOT/scripts/lib/base44-pinned-cli.sh"

if [[ -n "${BASE44_API_KEY:-}" ]]; then
  echo "Refusing Base44 owner login: BASE44_API_KEY must be unset for device-session authentication." >&2
  exit 2
fi

if [[ -z "$BASE44_EXPECTED_OWNER" || ${#BASE44_EXPECTED_OWNER} -gt 200 || "$BASE44_EXPECTED_OWNER" == *$'\n'* ]]; then
  echo "Refusing Base44 owner login: BASE44_EXPECTED_OWNER is missing or invalid." >&2
  exit 2
fi

if [[ -z "$APP_ID" || ${#APP_ID} -gt 160 || "$APP_ID" == *$'\n'* ]]; then
  echo "Refusing Base44 owner login: app identity is missing or invalid." >&2
  exit 2
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
chmod 700 "$TMP"

fixlist_install_base44_cli "$TMP"

# Run login from the protected temporary directory so any transient device-code
# file produced by the CLI can never land in the repository checkout.
cd "$TMP"
echo "BASE44_OWNER_DEVICE_LOGIN_REQUIRED"
echo "Approve the displayed device code at https://app.base44.com/login/device"
"$FIXLIST_BASE44_CLI" login

fixlist_require_base44_owner "$BASE44_EXPECTED_OWNER" "$TMP/whoami" "$APP_ID"

# whoami proves identity; this read-only inventory proves that exact identity can
# reach the exact FixList app before any production mutation is attempted.
if ! "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" functions list > "$TMP/functions" 2>&1; then
  echo "Refusing Base44 mutation: authenticated owner cannot access the configured app." >&2
  exit 2
fi

printf 'base44_owner_session=verified\nbase44_app_access=verified\n'
