#!/usr/bin/env bash
# Shared exact-source guard for owner/release mutations.
set -euo pipefail

fixlist_require_exact_main() {
  local repo_root="$1"
  local expected_sha="${2:-}"
  local confirm="${3:-}"

  local head remote event_sha
  head="$(git -C "$repo_root" rev-parse HEAD)"
  # A shallow actions/checkout of an exact SHA does not always materialize
  # refs/remotes/origin/main. In GitHub Actions the immutable push identity is
  # GITHUB_REF + GITHUB_SHA, so use that pair when the tracking ref is absent.
  # This is fail-closed: only an exact main push whose event SHA equals HEAD is
  # accepted. Local/manual release runs still refresh origin/main from GitHub.
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
    if git -C "$repo_root" rev-parse --verify refs/remotes/origin/main >/dev/null 2>&1; then
      remote="$(git -C "$repo_root" rev-parse refs/remotes/origin/main)"
      if [[ "$remote" != "$event_sha" ]]; then
        echo "Refusing: fetched origin/main does not equal the GitHub event SHA." >&2
        return 2
      fi
    else
      remote="$event_sha"
    fi
  else
    git -C "$repo_root" fetch origin main --quiet
    remote="$(git -C "$repo_root" rev-parse origin/main)"
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
