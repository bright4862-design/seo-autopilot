#!/usr/bin/env bash
# Bounded, source-pinned infrastructure operations for the inactive staged worker.
# No serving traffic, intake setting, owner cohort, or existing queue is changed.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO_ROOT/scripts/lib/release-source-guard.sh"

PROJECT="${GCP_PROJECT:-seo-autopilot-501517}"
REGION="${GCP_REGION:-europe-west1}"
SERVICE="${CLOUD_RUN_SERVICE:-fixlist-standard150-worker}"
OPERATION="${OPERATION:-verify-staged-scan-infra}"
SOURCE_SHA="${SOURCE_SHA:-}"
CONFIRM="${CONFIRM:-}"

[[ "$PROJECT" == seo-autopilot-501517 && "$REGION" == europe-west1 && "$SERVICE" == fixlist-standard150-worker ]] || {
  echo 'Refusing staged infrastructure operation outside the fixed FixList deployment.' >&2
  exit 2
}
case "$OPERATION" in
  prepare-staged-scan-infra)
    [[ "$CONFIRM" == "PREPARE-STAGED-SCAN-INFRA:$SOURCE_SHA" ]] || {
      echo 'Refusing staged provisioning: exact PREPARE-STAGED-SCAN-INFRA:<source-sha> confirmation required.' >&2
      exit 2
    }
    ;;
  verify-staged-scan-infra) ;;
  *) echo 'Refusing unsupported staged infrastructure operation.' >&2; exit 2 ;;
esac
[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo 'Exact SOURCE_SHA required.' >&2; exit 2; }
fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$SOURCE_SHA"

worker_metadata="$(gcloud run services describe "$SERVICE" --project="$PROJECT" --region="$REGION" --format=json)"
canonical_origin="$(python3 -c '
import json,sys
from urllib.parse import urlsplit
v=json.load(sys.stdin)
expected_sa="fixlist-standard150-worker@seo-autopilot-501517.iam.gserviceaccount.com"
if v.get("spec",{}).get("template",{}).get("spec",{}).get("serviceAccountName") != expected_sa:
    raise SystemExit("Unexpected worker runtime service account")
url=str(v.get("status",{}).get("url") or "")
p=urlsplit(url)
if p.scheme!="https" or not p.hostname or not p.hostname.endswith(".run.app") or "---" in p.hostname or p.username or p.password or p.port or p.path or p.query or p.fragment:
    raise SystemExit("Canonical Cloud Run origin unavailable")
print(url)
' <<< "$worker_metadata")"
tag="staged-${SOURCE_SHA:0:12}"
target_origin="https://${tag}---${canonical_origin#https://}"
python3 -c 'import sys; from urllib.parse import urlsplit; h=urlsplit(sys.argv[1]).hostname; sys.exit(0 if h and all(len(x)<=63 for x in h.split(".")) else "Staged target exceeds DNS label limit")' "$target_origin"

arguments=(
  --project "$PROJECT" --region "$REGION"
  --bucket fixlist-scan-workspaces-seo-autopilot-501517
  --queue fixlist-scan-stages
  --worker-sa fixlist-standard150-worker@seo-autopilot-501517.iam.gserviceaccount.com
  --invoker-sa fixlist-standard150-invoker@seo-autopilot-501517.iam.gserviceaccount.com
  --worker-url "$target_origin" --token-audience "$canonical_origin"
)
if [[ "$OPERATION" == prepare-staged-scan-infra ]]; then
  # The preparation script stops on any failure and never silently adopts an
  # existing resource. Inspect a partial bootstrap before continuing it.
  python3 "$REPO_ROOT/scripts/prepare_staged_scan_infra.py" "${arguments[@]}" --apply
fi
python3 "$REPO_ROOT/scripts/verify_staged_scan_infra.py" "${arguments[@]}" --expected-queue-state PAUSED
printf 'STAGED_INFRA_VERIFIED_INACTIVE source_sha=%s target=%s\n' "$SOURCE_SHA" "$target_origin"
