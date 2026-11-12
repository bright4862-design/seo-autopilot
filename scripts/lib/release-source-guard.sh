#!/usr/bin/env bash
# Shared exact-source guard for owner/release mutations.
set -euo pipefail

fixlist_require_exact_main() {
  local repo_root="$1"
  local expected_sha="${2:-}"
  local confirm="${3:-}"

  local head remote event_sha remote_row
  head="$(git -C "$repo_root" rev-parse HEAD)"
  # An Actions event SHA identifies its dispatched commit, not the current tip.
  # A cached (or absent) origin/main in actions/checkout cannot prove freshness.
  if [[ "${GITHUB_ACTIONS:-}" == "true" ]]; then
    if [[ "${GITHUB_REF:-}" != "refs/heads/main" ]]; then
      echo "Refusing: GitHub Actions release is not running from refs/heads/main." >&2
      return 2
    fi
    event_sha="${GITHUB_SHA:-}"
    if ! printf '%s' "$event_sha" | grep -Eq '^[0-9a-f]{40}$' || [[ "$event_sha" != "$head" ]]; then
      echo "Refusing: GitHub event SHA does not equal the checked-out HEAD." >&2
      return 2
    fi
  fi

  # Read authoritative origin/main, not its locally cached tracking ref.
  # This is a read-only remote request; network errors and missing refs refuse.
  if ! remote_row="$(GIT_TERMINAL_PROMPT=0 git -C "$repo_root" ls-remote --exit-code origin refs/heads/main)"; then
    echo "Refusing: cannot verify the current origin/main tip." >&2
    return 2
  fi
  remote="${remote_row%%$'\t'*}"
  if [[ ! "$remote" =~ ^[0-9a-f]{40}$ || "$remote_row" != "${remote}"$'\t'"refs/heads/main" ]]; then
    echo "Refusing: origin/main did not return one exact branch SHA." >&2
    return 2
  fi

  if ! printf '%s' "$head" | grep -Eq '^[0-9a-f]{40}$'; then
    echo "Refusing: checkout HEAD is not an exact 40-character Git SHA." >&2
    return 2
  fi
  if [[ "$head" != "$remote" ]]; then
    echo "Refusing: checkout $head is not current origin/main $remote." >&2
    return 2
  fi
  if [[ -n "$(git -C "$repo_root" status --porcelain --untracked-files=all)" ]]; then
    echo "Refusing: checkout is dirty." >&2
    return 2
  fi
  if [[ -n "$expected_sha" && "$head" != "$expected_sha" ]]; then
    echo "Refusing: SOURCE_SHA $expected_sha does not match checkout $head." >&2
    return 2
  fi
  if [[ -n "$expected_sha" && "$confirm" != "$expected_sha" ]]; then
    echo "Refusing: CONFIRM must equal exact SOURCE_SHA $expected_sha." >&2
    return 2
  fi
  FIXLIST_EXACT_SOURCE_SHA="$head"
  export FIXLIST_EXACT_SOURCE_SHA
  printf 'source_sha=%s\n' "$head"
}
