#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../base44"
base44 --app-id 6a498732ec779dfaaeab0e53 exec < ../scripts/tmp_gateway_probe.ts
