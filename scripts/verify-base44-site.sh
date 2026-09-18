#!/usr/bin/env bash
# Prove that the public customer site serves the exact release source.
#
# Both release paths call this with only EXPECTED_SOURCE_SHA set -- the site
# publish (deploy-base44-beta-site.sh) and the worker promotion gate
# (fixlist-cloud-operator.yml) -- so the defaults below ARE the canonical
# production hosts. Base44 now serves this app's own site at
# getfixlist.base44.app ("Visit your site at: https://getfixlist.base44.app",
# release run 35358749857); the retired rich-rank-pilot-flow.base44.app answers
# 404 and must never be the host that decides a release.
set -euo pipefail

EXPECTED_SOURCE_SHA="${EXPECTED_SOURCE_SHA:-}"
PUBLIC_URL="${PUBLIC_URL:-https://getfixlist.com/}"
BASE44_URL="${BASE44_URL:-https://getfixlist.base44.app/}"

if ! printf '%s' "$EXPECTED_SOURCE_SHA" | grep -Eq '^[0-9a-f]{40}$'; then
  echo "EXPECTED_SOURCE_SHA must be the exact 40-character source SHA." >&2
  exit 2
fi

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

verify_url() {
  local url="$1"
  local status html asset bundle
  # Read the HTTP status instead of letting --fail collapse every answer into
  # curl exit 22. A host that is not serving the app (a retired alias, an
  # unpublished site) is a different failure from a site serving the wrong
  # source, and the release log has to say which one happened.
  if ! status="$(curl --silent --show-error --max-time 30 \
    -H 'Cache-Control: no-cache' \
    -H 'Pragma: no-cache' \
    -o "$TMP/page.html" -w '%{http_code}' \
    "${url%/}/?fixlist_release_verify=${EXPECTED_SOURCE_SHA}")"; then
    echo "SITE_URL_UNREACHABLE url=$url" >&2
    return 1
  fi
  if [[ ! "$status" =~ ^2[0-9][0-9]$ ]]; then
    echo "SITE_URL_NOT_SERVING url=$url http_status=$status" >&2
    echo "This host is not serving the FixList app. That is a stale or unpublished site URL, not a source-SHA mismatch: compare it with the 'Visit your site at:' line printed by 'site deploy'." >&2
    return 3
  fi
  html="$(<"$TMP/page.html")"
  asset="$(grep -oE '/assets/index-[A-Za-z0-9_-]+\.js' <<<"$html" | head -1 || true)"
  if [[ -z "$asset" ]]; then
    echo "SITE BUNDLE NOT FOUND: $url" >&2
    return 1
  fi
  bundle="$(curl --fail --silent --show-error --max-time 30 \
    -H 'Cache-Control: no-cache' \
    -H 'Pragma: no-cache' \
    "${url%/}${asset}?fixlist_release_verify=${EXPECTED_SOURCE_SHA}")"
  if ! grep -Fq "$EXPECTED_SOURCE_SHA" <<<"$bundle"; then
    echo "SITE SOURCE SHA MISMATCH: $url$asset" >&2
    return 1
  fi
  printf 'SITE_SOURCE_SHA_VERIFIED %s%s\n' "$url" "$asset"
}

verify_url "$PUBLIC_URL"
verify_url "$BASE44_URL"
printf 'BASE44_SITE_SOURCE_VERIFIED source_sha=%s\n' "$EXPECTED_SOURCE_SHA"
