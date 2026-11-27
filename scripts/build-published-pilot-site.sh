#!/usr/bin/env bash
# Build only tracked files from the reviewed commit, using its dependency lock.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_sha="${1:-}" mode="${2:-}" destination="${3:-}"
[[ $# == 3 && "$source_sha" =~ ^[0-9a-f]{40}$ && "$source_sha" == "$(git -C "$root" rev-parse HEAD)" ]]
[[ "$mode" == PUBLISHED_PILOT || "$mode" == PAID_PILOT ]]
[[ "$destination" == /* && ! -e "$destination" && ! -L "$destination" ]]
mkdir -m 700 "$destination"
git -C "$root" archive "$source_sha" | tar -x -C "$destination"
cd "$destination"
timeout --kill-after=5s 180 npm ci --include=dev --no-audit --no-fund
node - <<'NODE'
const fs = require("node:fs");
const lock = require("./package-lock.json");
const sdk = JSON.parse(fs.readFileSync("node_modules/@base44/sdk/package.json", "utf8"));
if (!sdk.version || sdk.version !== lock.packages["node_modules/@base44/sdk"]?.version) {
  throw new Error("Installed Base44 SDK differs from the reviewed dependency lock");
}
NODE
unset VITE_BASE44_APP_BASE_URL BASE44_LEGACY_SDK_IMPORTS
VITE_SCAN_FUNCTION_GENERATION="$mode" VITE_BASE44_APP_ID=6a498732ec779dfaaeab0e53 \
  VITE_FIXLIST_SOURCE_SHA="$source_sha" timeout --kill-after=5s 120 npm run build
test -s dist/index.html
