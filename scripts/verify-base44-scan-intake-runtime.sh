#!/usr/bin/env bash
# Verify that the published startStandardScanJob runtime observes the requested
# intake state. The probe is authenticated and deliberately stops at project
# lookup, before any coordinator claim, ScanRun creation, or Cloud Task enqueue.
set -euo pipefail

APP_ID="${BASE44_APP_ID:-6a498732ec779dfaaeab0e53}"
ACTION="${ACTION:-}"
CLI="${FIXLIST_BASE44_CLI:-}"

case "$ACTION" in
  pause)
    EXPECTED_STATUS=503
    EXPECTED_CODE=scan_intake_paused
    ;;
  resume)
    EXPECTED_STATUS=404
    EXPECTED_CODE=project_not_found
    ;;
  *)
    echo "Refusing runtime intake verification: ACTION must be pause or resume." >&2
    exit 2
    ;;
esac

if [[ -z "$CLI" || ! -x "$CLI" ]]; then
  echo "Refusing runtime intake verification: FIXLIST_BASE44_CLI is unavailable." >&2
  exit 2
fi
if ! command -v deno >/dev/null 2>&1; then
  echo "Refusing runtime intake verification: deno is required for authenticated Base44 exec." >&2
  exit 2
fi
if ! command -v node >/dev/null 2>&1; then
  echo "Refusing runtime intake verification: node is required to validate the probe response." >&2
  exit 2
fi

probe_output="$(
  cat <<'JS' | "$CLI" --app-id "$APP_ID" exec --data-env prod
const requestId = "scanreq_intake_probe_" + crypto.randomUUID();
let status = 0;
let data = {};
try {
  const response = await base44.functions.invoke("startStandardScanJob", {
    request_id: requestId,
    idempotency_key: requestId,
    project_id: "fixlist-intake-probe-nonexistent",
    website_url: "https://example.com/",
    submitted_url: "https://example.com/",
    scan_mode: "standard_150",
    source: "intake_runtime_probe"
  });
  status = Number(response?.status || 0);
  data = response?.data || {};
} catch (error) {
  status = Number(error?.response?.status || 0);
  data = error?.response?.data || {};
}
console.log("FIXLIST_INTAKE_PROBE=" + JSON.stringify({
  status,
  accepted: data?.accepted === true,
  failure_code: String(data?.failure_code || ""),
  scan_id: String(data?.scan_id || data?.scan_run_id || "")
}));
JS
)"

probe_line="$(printf '%s\n' "$probe_output" | grep '^FIXLIST_INTAKE_PROBE=' | tail -1 || true)"
if [[ -z "$probe_line" ]]; then
  echo "Runtime intake probe did not return a verifiable result." >&2
  exit 1
fi
probe_json="${probe_line#FIXLIST_INTAKE_PROBE=}"

node - "$EXPECTED_STATUS" "$EXPECTED_CODE" "$probe_json" <<'NODE'
const [expectedStatus, expectedCode, raw] = process.argv.slice(2);
let value;
try {
  value = JSON.parse(raw);
} catch {
  console.error("Runtime intake probe returned invalid JSON.");
  process.exit(1);
}
if (Number(value.status) !== Number(expectedStatus)) {
  console.error(`Runtime intake probe status mismatch: expected ${expectedStatus}, got ${value.status}`);
  process.exit(1);
}
if (String(value.failure_code || "") !== expectedCode) {
  console.error(`Runtime intake probe code mismatch: expected ${expectedCode}, got ${value.failure_code || "(empty)"}`);
  process.exit(1);
}
if (value.accepted === true || String(value.scan_id || "")) {
  console.error("Runtime intake probe unexpectedly created or accepted a scan.");
  process.exit(1);
}
NODE

printf 'BASE44_SCAN_INTAKE_RUNTIME_VERIFIED\naction=%s\nexpected_code=%s\n' "$ACTION" "$EXPECTED_CODE"
