#!/usr/bin/env bash
# Prepare files only. The named publisher performs the separate live capture for a checkpoint input.
set -euo pipefail
umask 077
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
[[ $# == 3 ]] || { echo "Usage: preview-base44-provider-snapshot.sh SOURCE_SHA PUBLISHER_SNAPSHOT NEW_ABSOLUTE_DIRECTORY" >&2; exit 2; }
source_sha="$1"
capture_dir="$2"
output="$3"
legacy="$(<"$root/data/published-pilot-legacy-source")"
[[ "$legacy" =~ ^[a-f0-9]{40}$ ]] || exit 2
[[ "$source_sha" =~ ^[a-f0-9]{40}$ && "$output" == /* ]] || exit 2
[[ "$(git -C "$root" rev-parse "$source_sha^{commit}")" == "$source_sha" ]] || exit 2
git -C "$root" merge-base --is-ancestor "$legacy" "$source_sha"
identity="$(cat "$capture_dir/identity")"
capture_sha="$(sed -n '2p' "$capture_dir/identity")"
prior_sha="$(sed -n '3p' "$capture_dir/identity")"
[[ "$capture_sha" =~ ^[a-f0-9]{40}$ && "$prior_sha" =~ ^[a-f0-9]{40}$ && "$identity" == "$(printf '%s\n' 6a498732ec779dfaaeab0e53 "$capture_sha" "$prior_sha")" ]] || exit 2
git -C "$root" merge-base --is-ancestor "$capture_sha" "$source_sha"
git -C "$root" merge-base --is-ancestor "$prior_sha" "$capture_sha"
output_parent="$(cd "$(dirname "$output")" && pwd -P)"
[[ "$output_parent" != "$root" && "$output_parent" != "$root/"* ]] || exit 2
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir "$work/source" "$work/legacy"
git -C "$root" archive "$source_sha" | tar -x -C "$work/source"
git -C "$root" archive "$legacy" | tar -x -C "$work/legacy"
node "$root/scripts/lib/base44-provider-snapshot.mjs" "$work/source" "$work/legacy" "$capture_dir/before" "$output" "$source_sha" "$capture_sha" preview
