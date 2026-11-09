#!/usr/bin/env bash
# Prove the live release before creating a revision-specific, never-retargeted tag.
set -euo pipefail
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
revision="${GATEWAY_CANARY_REVISION:-}"
[[ "$revision" =~ ^fixlist-standard150-worker-[0-9]{5}-[a-z0-9]{3}$ ]] || { echo 'Exact canary revision required.' >&2; exit 2; }
[[ -n "${FIXLIST_WORKER_ID_TOKEN:-}" && -n "${FIXLIST_WORKER_TOKEN_AUDIENCE:-}" ]] || { echo 'Canary requires an invoker identity token and canonical audience.' >&2; exit 2; }
[[ "${SOURCE_SHA:-}" =~ ^[0-9a-f]{40}$ ]] || { echo 'Exact canary source SHA required.' >&2; exit 2; }
tag="canary-${revision#fixlist-standard150-worker-}"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
read_service() {
  gcloud run services describe "${CLOUD_RUN_SERVICE:-fixlist-standard150-worker}" \
    --project="${GCP_PROJECT:-seo-autopilot-501517}" --region="${GCP_REGION:-europe-west1}" --format=json > "$tmp/service.json"
}
read_service
# A dedicated tag is a permanent revision association. Never recycle or remove
# it: delayed watchdog tasks already carry this URL even after the gateway is off.
python3 - "$REPO_ROOT" "$tmp/service.json" "$revision" "$tag" <<'PY'
import json, sys
sys.path.insert(0, sys.argv[1])
from scripts.assert_tagged_zero_traffic_worker import CandidateNotIsolated, verify_tagged_zero_traffic
service=json.load(open(sys.argv[2])); revision,tag=sys.argv[3:]
entries=[e for e in service['status']['traffic'] if e.get('tag')==tag]
if entries:
    try: verify_tagged_zero_traffic(service, revision, tag)
    except CandidateNotIsolated as exc: raise SystemExit(str(exc))
PY
candidate_check="$(python3 "$REPO_ROOT/scripts/assert_tagged_zero_traffic_worker.py" --revision "$revision" < "$tmp/service.json")"
probe_url="${candidate_check##* tag_url=}"
export TARGET_REVISION="$revision" FIXLIST_WORKER_PROBE_URL="$probe_url"
# Existing verifier checks immutable source, fingerprint, complete markers,
# build provenance, V8 routes and timeout. A wrong runtime never gets a new tag.
OPERATION=verify-worker-routes bash "$REPO_ROOT/scripts/fixlist-cloud-operator.sh"
OPERATION=verify-worker-runtime-revision bash "$REPO_ROOT/scripts/fixlist-cloud-operator.sh"
gcloud run services update-traffic "${CLOUD_RUN_SERVICE:-fixlist-standard150-worker}" \
  --project="${GCP_PROJECT:-seo-autopilot-501517}" --region="${GCP_REGION:-europe-west1}" \
  --update-tags="${tag}=${revision}" --quiet
read_service
pinned="$(python3 "$REPO_ROOT/scripts/assert_tagged_zero_traffic_worker.py" --revision "$revision" --tag "$tag" < "$tmp/service.json")"
export FIXLIST_WORKER_PROBE_URL="${pinned##* tag_url=}"
OPERATION=verify-worker-runtime-revision bash "$REPO_ROOT/scripts/fixlist-cloud-operator.sh"
printf 'GATEWAY_CANARY_WORKER_ORIGIN=%s\n' "$FIXLIST_WORKER_PROBE_URL"
