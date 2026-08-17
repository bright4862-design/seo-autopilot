#!/usr/bin/env bash
# Shared exact-source guard for owner/release mutations.
set -euo pipefail

fixlist_require_exact_main() {
  local repo_root="$1"
  local expected_sha="${2:-}"
  local confirm="${3:-}"

  # The Cloud Operator checks out with persist-credentials: false, so a network
  # fetch here has no credentials and aborts the entire release with git exit
  # 128 ("could not read Username") on this private repo. fetch-depth: 0 has
  # already populated refs/remotes/origin/*, so refresh opportunistically --
  # which is what keeps a local operator honest against a stale ref -- and fall
  # back to the checkout's own remote-tracking ref in CI.
  git -C "$repo_root" fetch origin main --quiet 2>/dev/null || true
  if ! git -C "$repo_root" rev-parse --verify --quiet origin/main >/dev/null; then
    echo "Refusing: origin/main is not present in this checkout." >&2
    return 2
  fi
  local head remote
  head="$(git -C "$repo_root" rev-parse HEAD)"
  remote="$(git -C "$repo_root" rev-parse origin/main)"

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
