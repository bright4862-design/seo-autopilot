#!/usr/bin/env bash
set -euo pipefail

EXPECTED_SOURCE_SHA="${EXPECTED_SOURCE_SHA:-}"
PUBLIC_URL="${PUBLIC_URL:-https://getfixlist.com/}"
BASE44_URL="${BASE44_URL:-https://rich-rank-pilot-flow.base44.app/}"

if ! printf '%s' "$EXPECTED_SOURCE_SHA" | grep -Eq '^[0-9a-f]{40}$'; then
  echo "EXPECTED_SOURCE_SHA must be the exact 40-character source SHA." >&2
  exit 2
fi

verify_url() {
  local url="$1"
  local html
  html="$(curl --fail --silent --show-error --max-time 30 \
    -H 'Cache-Control: no-cache' \
    -H 'Pragma: no-cache' \
    "${url}?fixlist_release_verify=${EXPECTED_SOURCE_SHA}")"
  if ! grep -Fq "<meta name=\"fixlist-source-sha\" content=\"${EXPECTED_SOURCE_SHA}\"" <<<"$html"; then
    echo "SITE SOURCE SHA MISMATCH: $url" >&2
    return 1
  fi
  printf 'SITE_SOURCE_SHA_VERIFIED %s\n' "$url"
}

verify_url "$PUBLIC_URL"
verify_url "$BASE44_URL"
printf 'BASE44_SITE_SOURCE_VERIFIED source_sha=%s\n' "$EXPECTED_SOURCE_SHA"
