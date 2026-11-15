#!/usr/bin/env bash
# Prove the live release before creating a revision-specific, never-retargeted tag.
set -euo pipefail
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
revision="${GATEWAY_CANARY_REVISION:-}"
[[ "$revision" =~ ^fixlist-standard150-worker-[0-9]{5}-[a-z0-9]{3}$ ]] || { echo 'Exact canary revision required.' >&2; exit 2; }
[[ -n "${FIXLIST_WORKER_ID_TOKEN:-}" && -n "${FIXLIST_WORKER_TOKEN_AUDIENCE:-}" ]] || { echo 'Canary requires an invoker identity token and canonical audience.' >&2; exit 2; }
[[ "${SOURCE_SHA:-}" =~ ^[0-9a-f]{40}$ ]] || { echo 'Exact canary source SHA required.' >&2; exit 2; }
require_staged="${GATEWAY_REQUIRE_STAGED_RUNTIME:-0}"
[[ "$require_staged" == 0 || "$require_staged" == 1 ]] || { echo 'Invalid staged runtime proof requirement.' >&2; exit 2; }
tag="canary-${revision#fixlist-standard150-worker-}"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
read_service() {
  gcloud run services describe "${CLOUD_RUN_SERVICE:-fixlist-standard150-worker}" \
    --project="${GCP_PROJECT:-seo-autopilot-501517}" --region="${GCP_REGION:-europe-west1}" --format=json > "$tmp/service.json"
}
read_service
gcloud run revisions describe "$revision" --project="${GCP_PROJECT:-seo-autopilot-501517}" \
  --region="${GCP_REGION:-europe-west1}" --format=json > "$tmp/revision.json"
probe_tag="$(python3 - "$tmp/service.json" "$tmp/revision.json" "$revision" "$SOURCE_SHA" "$require_staged" <<'PY'
import json, sys
service, worker = [json.load(open(path)) for path in sys.argv[1:3]]
revision, source, required = sys.argv[3:]
if worker['metadata']['name'] != revision:
    raise SystemExit('Canary worker revision readback mismatch.')
containers = worker['spec']['containers']
if len(containers) != 1:
    raise SystemExit('Canary worker must have one container.')
stage_fields = {'FIXLIST_STAGED_CONFIG_SHA256', 'SCAN_WORKSPACE_BUCKET', 'SCAN_STAGE_TASKS_QUEUE_PATH',
                'SCAN_STAGE_TARGET_URL', 'SCAN_STAGE_TOKEN_AUDIENCE'}
has_stage_config = any((entry.get('name') in stage_fields and (entry.get('value') or entry.get('valueFrom')))
                       or (entry.get('name') == 'SCAN_PIPELINE_MODE' and entry.get('value') == 'staged')
                       for entry in containers[0].get('env', []))
has_stage_tag = any(entry.get('revisionName') == revision and str(entry.get('tag', '')).startswith('staged-')
                    for entry in service['status']['traffic'])
print(f'staged-{source[:12]}' if required == '1' or has_stage_config or has_stage_tag else 'candidate')
PY
)"
probe_args=(--revision "$revision" --tag "$probe_tag")
if [[ "$probe_tag" == staged-* ]]; then
  probe_args+=(--source-sha "$SOURCE_SHA")
  require_staged=1
fi

# A dedicated tag is a permanent revision association. Never recycle or remove
# it: delayed watchdog tasks already carry this URL even after the gateway is off.
verify_existing_tag() {
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
}
verify_existing_tag
candidate_check="$(python3 "$REPO_ROOT/scripts/assert_tagged_zero_traffic_worker.py" "${probe_args[@]}" < "$tmp/service.json")"
probe_url="${candidate_check##* tag_url=}"
export TARGET_REVISION="$revision" FIXLIST_WORKER_PROBE_URL="$probe_url"
# Existing verifier checks immutable source, fingerprint, complete markers,
# build provenance, V8 routes and timeout. Staged workers must also prove the
# signed Base44 runtime before exposing a new gateway target.
OPERATION=verify-worker-routes bash "$REPO_ROOT/scripts/fixlist-cloud-operator.sh"
OPERATION=verify-worker-runtime-revision FIXLIST_VERIFY_STAGED_BASE44_RUNTIME="$require_staged" \
  bash "$REPO_ROOT/scripts/fixlist-cloud-operator.sh"
read_service
verify_existing_tag
current="$(python3 "$REPO_ROOT/scripts/assert_tagged_zero_traffic_worker.py" "${probe_args[@]}" < "$tmp/service.json")"
[[ "${current##* tag_url=}" == "$probe_url" ]] || { echo 'Canary proof target changed before tagging.' >&2; exit 2; }
gcloud run services update-traffic "${CLOUD_RUN_SERVICE:-fixlist-standard150-worker}" \
  --project="${GCP_PROJECT:-seo-autopilot-501517}" --region="${GCP_REGION:-europe-west1}" \
  --update-tags="${tag}=${revision}" --quiet
read_service
pinned="$(python3 "$REPO_ROOT/scripts/assert_tagged_zero_traffic_worker.py" --revision "$revision" --tag "$tag" < "$tmp/service.json")"
export FIXLIST_WORKER_PROBE_URL="${pinned##* tag_url=}"
OPERATION=verify-worker-runtime-revision FIXLIST_VERIFY_STAGED_BASE44_RUNTIME="$require_staged" \
  bash "$REPO_ROOT/scripts/fixlist-cloud-operator.sh"
printf 'GATEWAY_CANARY_WORKER_ORIGIN=%s\nGATEWAY_CANARY_STAGED_RUNTIME_REQUIRED=%s\n' \
  "$FIXLIST_WORKER_PROBE_URL" "$require_staged"
