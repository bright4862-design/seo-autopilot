#!/usr/bin/env bash
# Assemble a minimal gateway Docker context from one exact committed tree.
# This only packages files. Deployment authorization/source guards remain in
# deploy_dispatch_gateway.sh; CI may package an immutable PR head for validation.
set -euo pipefail

[[ "$#" -eq 2 ]] || { echo "Usage: package_dispatch_gateway.sh <exact-commit-sha> <new-destination>" >&2; exit 2; }
PACKAGE_SHA="$1"
DESTINATION="$2"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if ! [[ "$PACKAGE_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Gateway package source must be an exact 40-character lowercase commit SHA." >&2
  exit 2
fi
git -C "$REPO_ROOT" cat-file -e "${PACKAGE_SHA}^{commit}"
if [[ -z "$DESTINATION" || -e "$DESTINATION" || -L "$DESTINATION" ]]; then
  echo "Gateway package destination must be a new directory." >&2
  exit 2
fi

ARCHIVE_DIR="$(mktemp -d)"
trap 'rm -rf "$ARCHIVE_DIR"' EXIT
COMPARISON_MODULES=(
  __init__.py authority_seal.py repair_coverage.py repair_identity.py
  missing_h1_comparison_contract.py
  scan_comparison.py scan_comparison_integrity.py scan_comparison_authority.py
)
ARCHIVE_PATHS=(dispatch-gateway)
for module in "${COMPARISON_MODULES[@]}"; do
  ARCHIVE_PATHS+=("scanner-api/app/$module")
done
git -C "$REPO_ROOT" archive --format=tar "$PACKAGE_SHA" "${ARCHIVE_PATHS[@]}" \
  | tar -xf - -C "$ARCHIVE_DIR"

mkdir "$DESTINATION"
mkdir "$DESTINATION/app"
for file in main.py requirements.txt Dockerfile test_gateway.py; do
  cp "$ARCHIVE_DIR/dispatch-gateway/$file" "$DESTINATION/$file"
done
for module in "${COMPARISON_MODULES[@]}"; do
  cp "$ARCHIVE_DIR/scanner-api/app/$module" "$DESTINATION/app/$module"
done
printf '%s\n' "$PACKAGE_SHA" > "$DESTINATION/.fixlist-source-sha"
