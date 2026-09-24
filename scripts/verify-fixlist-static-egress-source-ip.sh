#!/usr/bin/env bash
set -euo pipefail

PROJECT="${GCP_PROJECT:-seo-autopilot-501517}"
REGION="${GCP_REGION:-europe-west1}"
WORKER="${CLOUD_RUN_SERVICE:-fixlist-standard150-worker}"
SOURCE_SHA="${SOURCE_SHA:-}"
TARGET_REVISION="${TARGET_REVISION:-}"
CONFIRM="${CONFIRM:-}"
NETWORK="${FIXLIST_EGRESS_NETWORK:-fixlist-scanner-egress}"
SUBNET="${FIXLIST_EGRESS_SUBNET:-fixlist-scanner-egress-euw1}"
ADDRESS="${FIXLIST_EGRESS_ADDRESS:-fixlist-scanner-egress-ip-a}"
RUN_ID="${GITHUB_RUN_ID:-manual}"
ATTEMPT="${GITHUB_RUN_ATTEMPT:-1}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO_ROOT/scripts/lib/release-source-guard.sh"
fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$SOURCE_SHA"

if [[ ! "$TARGET_REVISION" =~ ^fixlist-standard150-worker-[a-z0-9-]+$ ]]; then
  echo "Refusing: exact worker revision required." >&2
  exit 2
fi
if [[ "$CONFIRM" != "STATIC-EGRESS-PROBE:$TARGET_REVISION:$SOURCE_SHA" ]]; then
  echo "Refusing: confirmation does not bind revision + source SHA." >&2
  exit 2
fi

"$REPO_ROOT/scripts/verify-fixlist-static-egress-canary.sh" >/dev/null

tmp="$(mktemp -d)"
job="fixlist-egress-probe-${RUN_ID}-${ATTEMPT}"
cleanup() {
  gcloud run jobs delete "$job" --project="$PROJECT" --region="$REGION" --quiet >/dev/null 2>&1 || true
  rm -rf "$tmp"
}
trap cleanup EXIT

gcloud run revisions describe "$TARGET_REVISION"   --project="$PROJECT" --region="$REGION" --format=json > "$tmp/revision.json"
gcloud run services describe "$WORKER"   --project="$PROJECT" --region="$REGION" --format=json > "$tmp/service.json"

readarray -t values < <(python3 - "$tmp/revision.json" "$tmp/service.json" "$SOURCE_SHA" "$NETWORK" "$SUBNET" <<'PY'
import json, sys
rev_path, service_path, source_sha, network, subnet = sys.argv[1:]
rev=json.load(open(rev_path, encoding="utf-8"))
service=json.load(open(service_path, encoding="utf-8"))
spec=rev.get("spec", {}) or {}
container=(spec.get("containers") or [{}])[0]
env={item.get("name"): item.get("value","") for item in container.get("env", [])}
if env.get("FIXLIST_WORKER_SOURCE_SHA") != source_sha:
    raise SystemExit("candidate source SHA mismatch")
if env.get("FIXLIST_EGRESS_MODE") != "static-canary":
    raise SystemExit("candidate is not static-canary mode")
ann=rev.get("metadata",{}).get("annotations",{}) or {}
try:
    interfaces=json.loads(ann.get("run.googleapis.com/network-interfaces",""))
except Exception:
    raise SystemExit("candidate Direct VPC interface is missing")
if len(interfaces)!=1:
    raise SystemExit("candidate must carry exactly one Direct VPC interface")
item=interfaces[0]
if str(item.get("network","")).split("/")[-1] != network:
    raise SystemExit("candidate network mismatch")
if str(item.get("subnetwork","")).split("/")[-1] != subnet:
    raise SystemExit("candidate subnet mismatch")
if ann.get("run.googleapis.com/vpc-access-egress") != "all-traffic":
    raise SystemExit("candidate is not all-traffic VPC egress")
name=rev.get("metadata",{}).get("name","")
traffic=service.get("status",{}).get("traffic",[]) or []
percent=sum(int(t.get("percent") or 0) for t in traffic if t.get("revisionName")==name)
if percent != 0:
    raise SystemExit("candidate unexpectedly serves customer traffic")
image=str(rev.get("status",{}).get("imageDigest") or container.get("image") or "")
if "@sha256:" not in image:
    raise SystemExit("candidate immutable image digest unavailable")
sa=str(spec.get("serviceAccountName") or "")
if not sa:
    raise SystemExit("candidate runtime service account unavailable")
print(image)
print(sa)
PY
)
[[ "${#values[@]}" -eq 2 ]] || { echo "Refusing: candidate probe inputs incomplete." >&2; exit 2; }
IMAGE="${values[0]}"
RUNTIME_SA="${values[1]}"
EXPECTED_IP="$(gcloud compute addresses describe "$ADDRESS" --project="$PROJECT" --region="$REGION" --format='value(address)')"
[[ "$EXPECTED_IP" =~ ^[0-9]+.[0-9]+.[0-9]+.[0-9]+$ ]] || { echo "Refusing: reserved egress IPv4 unavailable." >&2; exit 2; }

probe_python='import json, urllib.request; ip=urllib.request.urlopen("https://api.ipify.org", timeout=20).read().decode().strip(); print("FIXLIST_STATIC_EGRESS_PROBE="+json.dumps({"source_ip":ip}, separators=(",",":")), flush=True)'
encoded="$(printf '%s' "$probe_python" | base64 | tr -d '\n')"
args="import base64; exec(compile(base64.b64decode('$encoded'), 'fixlist_static_egress_probe.py', 'exec'))"

gcloud run jobs create "$job"   --project="$PROJECT" --region="$REGION"   --image="$IMAGE"   --service-account="$RUNTIME_SA"   --tasks=1 --parallelism=1 --max-retries=0 --task-timeout=90s   --cpu=1 --memory=512Mi   --command=python   --args=-c,"$args"   --network="$NETWORK"   --subnet="$SUBNET"   --vpc-egress=all-traffic   --labels=purpose=fixlist-static-egress-probe   --quiet

execution="$(gcloud run jobs execute "$job" --project="$PROJECT" --region="$REGION" --wait --format='value(metadata.name)')"
[[ -n "$execution" ]] || { echo "Static egress probe execution identity missing." >&2; exit 2; }

gcloud logging read   "resource.type=\"cloud_run_job\" AND resource.labels.job_name=\"$job\" AND labels.\"run.googleapis.com/execution_name\"=\"$execution\""   --project="$PROJECT" --limit=50 --order=asc --format='value(textPayload)' > "$tmp/logs.txt"

observed="$(python3 - "$tmp/logs.txt" <<'PY'
import json, sys
for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    line=line.strip()
    prefix="FIXLIST_STATIC_EGRESS_PROBE="
    if not line.startswith(prefix):
        continue
    try:
        value=json.loads(line[len(prefix):])
    except Exception:
        continue
    ip=str(value.get("source_ip") or "")
    if ip:
        print(ip)
        break
PY
)"
[[ -n "$observed" ]] || { echo "Static egress probe produced no attributable source IP." >&2; exit 2; }
if [[ "$observed" != "$EXPECTED_IP" ]]; then
  echo "Static egress probe mismatch: observed $observed but reserved canary IP is $EXPECTED_IP." >&2
  exit 2
fi

echo "STATIC_EGRESS_SOURCE_IP_VERIFIED=1"
echo "STATIC_EGRESS_REVISION=$TARGET_REVISION"
echo "STATIC_EGRESS_IP=$observed"
