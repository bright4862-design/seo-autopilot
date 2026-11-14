#!/usr/bin/env bash
# Read the deployed candidate packages, schemas, and the actual V9 intake.
set -euo pipefail
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_SHA="${SOURCE_SHA:-}"
OWNER_ID="${EXPECTED_OWNER_USER_ID:-}"
OUTPUT="${BASE44_OBSERVATIONS_DIR:-}"
APP_ID="6a498732ec779dfaaeab0e53"
[[ "$OWNER_ID" == 6a498da58ef5cec1f5cd4486 && "${BASE44_APP_ID:-$APP_ID}" == "$APP_ID" ]] || {
  echo 'Refusing: FixList owner and app identity required.' >&2
  exit 2
}
source "$ROOT/scripts/lib/release-source-guard.sh"
source "$ROOT/scripts/lib/base44-pinned-cli.sh"
fixlist_require_exact_main "$ROOT" "$SOURCE_SHA" "$SOURCE_SHA"
node --input-type=module - "$ROOT" "$OUTPUT" <<'NODE'
import fs from 'node:fs';
import path from 'node:path';
const [root, output] = process.argv.slice(2);
if (!path.isAbsolute(output) || fs.realpathSync(output) !== output || !fs.statSync(output).isDirectory()) {
  throw new Error('Canonical existing observation directory required');
}
const relative = path.relative(root, output);
if (relative !== '..' && !relative.startsWith('../')) throw new Error('Use an external observation directory');
for (const name of ['packages.json', 'schemas.json', 'intake.json']) {
  if (fs.lstatSync(path.join(output, name), { throwIfNoEntry: false })) throw new Error('Observation output already exists');
}
NODE
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fixlist_install_base44_cli "$TMP/cli"
fixlist_require_base44_owner "${BASE44_EXPECTED_OWNER:-}" "$TMP/whoami" "$APP_ID"
if ! timeout --signal=TERM --kill-after=5s 55 "$FIXLIST_BASE44_CLI" --app-id "$APP_ID" exec --data-env prod \
    > "$TMP/intake.out" 2> "$TMP/intake.err" <<'JS'
const reply = await base44.functions.invoke("startStandardScanJobV9", { action: "staged_runtime_status" });
const body = reply?.data && typeof reply.data === "object" ? reply.data : reply;
if (body?.schema_version !== "fixlist_staged_v9_intake_readback_v1" || body?.success !== true) {
  throw new Error("V9 intake readback unavailable");
}
const keys = ["schema_version", "success", "observed_at", "build_id", "runtime_activation_id", "release_fingerprint",
  "configured_pipeline_mode", "pipeline_mode", "staged_owner_cohort_state", "staged_owner_count",
  "staged_owner_cohort_sha256", "staged_owner_enabled", "intake_gate", "admission_gate"];
const safe = Object.fromEntries(keys.map(key => [key, body[key]]));
console.log("FIXLIST_V9_INTAKE_READBACK=" + JSON.stringify(safe));
JS
then
  echo 'V9 intake readback failed. No scan was submitted.' >&2
  exit 1
fi
CONFIRM="VERIFY-BASE44-STAGED-V9:$SOURCE_SHA" READINESS_OUTPUT="$OUTPUT/packages.json" \
  bash "$ROOT/scripts/deploy-base44-staged-functions.sh" verify
node --input-type=module - "$TMP/intake.out" "$OUTPUT/packages.json" "$OUTPUT/intake.json" <<'NODE'
import fs from 'node:fs';
const [input, packagesPath, output] = process.argv.slice(2);
const prefix = 'FIXLIST_V9_INTAKE_READBACK=';
const rows = fs.readFileSync(input, 'utf8').split('\n').filter(line => line.startsWith(prefix));
if (rows.length !== 1) throw new Error('V9 intake readback missing or ambiguous');
const report = JSON.parse(rows[0].slice(prefix.length));
const packages = JSON.parse(fs.readFileSync(packagesPath, 'utf8'));
const intake = packages.functions.find(row => row.name === 'startStandardScanJobV9');
const fields = ['schema_version', 'success', 'observed_at', 'build_id', 'runtime_activation_id',
  'release_fingerprint', 'configured_pipeline_mode', 'pipeline_mode', 'staged_owner_cohort_state',
  'staged_owner_count', 'staged_owner_cohort_sha256', 'staged_owner_enabled', 'intake_gate', 'admission_gate'];
const enumValue = (key, allowed) => allowed.includes(report[key]);
if (report.schema_version !== 'fixlist_staged_v9_intake_readback_v1' || report.success !== true
    || !/^[a-f0-9]{64}$/.test(report.build_id || '') || !/^[a-f0-9]{16}$/.test(report.release_fingerprint || '')
    || report.build_id !== intake?.build_id || report.runtime_activation_id !== intake?.runtime_activation_id
    || report.release_fingerprint !== packages.candidate_fingerprint
    || !Number.isFinite(Date.parse(report.observed_at))
    || !enumValue('configured_pipeline_mode', ['staged', 'monolith', 'absent', 'invalid', 'unavailable'])
    || !enumValue('pipeline_mode', ['staged', 'monolith'])
    || !enumValue('staged_owner_cohort_state', ['explicit', 'empty', 'absent', 'invalid', 'unavailable'])
    || !Number.isSafeInteger(report.staged_owner_count) || report.staged_owner_count < 0
    || !/^[a-f0-9]{64}$/.test(report.staged_owner_cohort_sha256 || '')
    || typeof report.staged_owner_enabled !== 'boolean'
    || !['intake_gate', 'admission_gate'].every(key => enumValue(key, ['enabled', 'disabled', 'unavailable']))) {
  throw new Error('V9 intake readback shape mismatch');
}
const safe = Object.fromEntries(fields.map(key => [key, report[key]]));
fs.writeFileSync(output, JSON.stringify(safe, null, 2) + '\n', { flag: 'wx', mode: 0o600 });
NODE
node "$ROOT/scripts/base44_staged_schema.mjs" verify --source-sha "$SOURCE_SHA" --report "$OUTPUT/schemas.json"
