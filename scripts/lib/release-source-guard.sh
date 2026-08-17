#!/usr/bin/env bash
# Shared exact-source guard for owner/release mutations.
set -euo pipefail

fixlist_require_exact_main() {
  local repo_root="$1"
  local expected_sha="${2:-}"
  local confirm="${3:-}"

  local head remote
  # actions/checkout fetches origin/main before removing its temporary GitHub
  # credential. In GitHub Actions, verify that already-fetched ref locally so
  # the exact-source guard does not require a second authenticated network
  # fetch. Local/manual release runs still refresh origin/main from GitHub.
  if [[ "${GITHUB_ACTIONS:-}" == "true" ]]; then
    remote="$(git -C "$repo_root" rev-parse refs/remotes/origin/main)"
  else
    git -C "$repo_root" fetch origin main --quiet
    remote="$(git -C "$repo_root" rev-parse origin/main)"
  fi
  head="$(git -C "$repo_root" rev-parse HEAD)"

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
