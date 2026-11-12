#!/usr/bin/env bash
# The existing site-and-functions publisher verifies the V8 release, not an
# independently accepted V9 site cutover. Prevent ambient Vite variables or
# .env.production from silently switching its browser routes to V9.
fixlist_require_v8_site_generation() {
  if [[ "${VITE_SCAN_FUNCTION_GENERATION:-V8}" != "V8" ]]; then
    echo "Refusing V8 site publication: VITE_SCAN_FUNCTION_GENERATION must be unset or V8; V9 requires its own accepted site cutover." >&2
    return 2
  fi
  # Process environment has precedence over Vite .env files. Export V8 so
  # no local production-mode file can silently select the candidate routes.
  export VITE_SCAN_FUNCTION_GENERATION=V8
}
