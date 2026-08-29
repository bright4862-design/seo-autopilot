#!/usr/bin/env bash
set -euo pipefail

APP_ID="${BASE44_APP_ID:-6a498732ec779dfaaeab0e53}"
API_URL="${BASE44_API_URL:-https://base44.app}"
FUNCTION_NAME="durableScanWorkerControl"
WORKER_USER_AGENT='Mozilla/5.0 (compatible; FixListStandard150Worker/1.0; +https://getfixlist.com)'

if [[ ! "$APP_ID" =~ ^[A-Za-z0-9_-]{6,160}$ ]]; then
  echo "Invalid Base44 app id." >&2
  exit 2
fi
case "$API_URL" in
  https://*) ;;
  *) echo "Base44 API URL must use HTTPS." >&2; exit 2 ;;
esac
API_URL="${API_URL%/}"
URL="$API_URL/api/apps/$APP_ID/functions/$FUNCTION_NAME"

BODY_FILE="$(mktemp)"
HEADER_FILE="$(mktemp)"
trap 'rm -f "$BODY_FILE" "$HEADER_FILE"' EXIT

code="$(curl --silent --show-error --max-time 20   --output "$BODY_FILE"   --dump-header "$HEADER_FILE"   --write-out '%{http_code}'   --request POST "$URL"   --header 'content-type: application/json'   --header 'X-FixList-Worker: invalid_route_probe'   --header "User-Agent: $WORKER_USER_AGENT"   --data-binary '{"version":"invalid_route_probe"}')"

readarray -t parsed < <(python3 - "$BODY_FILE" "$HEADER_FILE" <<'PY'
import json, sys
body_path, header_path = sys.argv[1:]
try:
    body = json.load(open(body_path, encoding="utf-8"))
except Exception:
    body = {}
headers = {}
for raw in open(header_path, encoding="utf-8", errors="replace"):
    if ":" not in raw:
        continue
    key, value = raw.split(":", 1)
    headers[key.strip().lower()] = value.strip()
print(str(body.get("error_code") or ""))
print(str(headers.get("content-type") or "").split(";", 1)[0][:120])
print(str(headers.get("cf-ray") or "")[:160])
PY
)

error_code="${parsed[0]:-}"
content_type="${parsed[1]:-}"
cf_ray="${parsed[2]:-}"

printf 'BASE44_CONTROL_ROUTE_PROBE status=%s error_code=%s content_type=%s cf_ray=%s\n'   "$code" "$error_code" "$content_type" "${cf_ray:-none}"

if [[ "$code" != "403" || "$error_code" != "worker_header_invalid" ]]; then
  echo "Refusing release: durableScanWorkerControl is not publicly routable to the deployed function." >&2
  exit 1
fi

echo "BASE44_CONTROL_ROUTE_VERIFIED"
