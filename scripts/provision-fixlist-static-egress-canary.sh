#!/usr/bin/env bash
set -euo pipefail

PROJECT="${GCP_PROJECT:-seo-autopilot-501517}"
REGION="${GCP_REGION:-europe-west1}"
SOURCE_SHA="${SOURCE_SHA:-}"
CONFIRM="${CONFIRM:-}"
NETWORK="${FIXLIST_EGRESS_NETWORK:-fixlist-scanner-egress}"
SUBNET="${FIXLIST_EGRESS_SUBNET:-fixlist-scanner-egress-euw1}"
SUBNET_CIDR="${FIXLIST_EGRESS_SUBNET_CIDR:-10.210.0.0/26}"
ROUTER="${FIXLIST_EGRESS_ROUTER:-fixlist-scanner-egress-router}"
NAT="${FIXLIST_EGRESS_NAT:-fixlist-scanner-egress-nat-a}"
ADDRESS="${FIXLIST_EGRESS_ADDRESS:-fixlist-scanner-egress-ip-a}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO_ROOT/scripts/lib/release-source-guard.sh"
fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$SOURCE_SHA"

if [[ "$CONFIRM" != "STATIC-EGRESS-CANARY:$SOURCE_SHA" ]]; then
  echo "Refusing: CONFIRM must equal STATIC-EGRESS-CANARY:$SOURCE_SHA" >&2
  exit 2
fi
[[ "$REGION" == "europe-west1" ]] || { echo "Refusing: static egress canary is pinned to europe-west1." >&2; exit 2; }
[[ "$SUBNET_CIDR" == */26 ]] || { echo "Refusing: Direct VPC egress subnet must be /26 for this canary." >&2; exit 2; }

gcloud config set project "$PROJECT" >/dev/null

if ! gcloud compute networks describe "$NETWORK" --project="$PROJECT" >/dev/null 2>&1; then
  gcloud compute networks create "$NETWORK"     --project="$PROJECT"     --subnet-mode=custom     --bgp-routing-mode=regional     --quiet
fi
network_mode="$(gcloud compute networks describe "$NETWORK" --project="$PROJECT" --format='value(autoCreateSubnetworks)')"
[[ "$network_mode" == "False" || "$network_mode" == "false" ]] || {
  echo "Refusing: existing egress network is not custom-mode." >&2
  exit 2
}

if ! gcloud compute networks subnets describe "$SUBNET" --project="$PROJECT" --region="$REGION" >/dev/null 2>&1; then
  gcloud compute networks subnets create "$SUBNET"     --project="$PROJECT"     --region="$REGION"     --network="$NETWORK"     --range="$SUBNET_CIDR"     --enable-private-ip-google-access     --quiet
fi
subnet_json="$(mktemp)"
trap 'rm -f "$subnet_json"' EXIT
gcloud compute networks subnets describe "$SUBNET" --project="$PROJECT" --region="$REGION" --format=json > "$subnet_json"
python3 - "$subnet_json" "$NETWORK" "$SUBNET_CIDR" <<'PY'
import json, sys
path, network, cidr = sys.argv[1:]
value = json.load(open(path, encoding="utf-8"))
if value.get("ipCidrRange") != cidr:
    raise SystemExit("Refusing: existing egress subnet CIDR differs from canary contract")
if not str(value.get("network") or "").endswith("/networks/" + network):
    raise SystemExit("Refusing: existing egress subnet belongs to another network")
PY

# Same-project Direct VPC egress uses the existing Cloud Run service-agent
# permissions. This canary provisioner deliberately does not mutate project or
# subnet IAM; a missing service-agent permission must fail at worker staging
# rather than broadening operator access here.

if ! gcloud compute addresses describe "$ADDRESS" --project="$PROJECT" --region="$REGION" >/dev/null 2>&1; then
  gcloud compute addresses create "$ADDRESS"     --project="$PROJECT"     --region="$REGION"     --network-tier=PREMIUM     --quiet
fi
address_json="$(mktemp)"
gcloud compute addresses describe "$ADDRESS" --project="$PROJECT" --region="$REGION" --format=json > "$address_json"
python3 - "$address_json" "$REGION" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
if value.get("addressType") != "EXTERNAL":
    raise SystemExit("Refusing: canary NAT address is not EXTERNAL")
if value.get("networkTier") != "PREMIUM":
    raise SystemExit("Refusing: canary NAT address is not PREMIUM tier")
if not str(value.get("region") or "").endswith("/regions/" + sys.argv[2]):
    raise SystemExit("Refusing: canary NAT address is in the wrong region")
PY
rm -f "$address_json"

if ! gcloud compute routers describe "$ROUTER" --project="$PROJECT" --region="$REGION" >/dev/null 2>&1; then
  gcloud compute routers create "$ROUTER"     --project="$PROJECT"     --region="$REGION"     --network="$NETWORK"     --quiet
fi
router_network="$(gcloud compute routers describe "$ROUTER" --project="$PROJECT" --region="$REGION" --format='value(network)')"
[[ "$router_network" == */networks/"$NETWORK" ]] || {
  echo "Refusing: existing egress router belongs to another network." >&2
  exit 2
}

if ! gcloud compute routers nats describe "$NAT" --router="$ROUTER" --project="$PROJECT" --region="$REGION" >/dev/null 2>&1; then
  gcloud compute routers nats create "$NAT"     --router="$ROUTER"     --project="$PROJECT"     --region="$REGION"     --nat-custom-subnet-ip-ranges="$SUBNET:ALL"     --nat-external-ip-pool="$ADDRESS"     --enable-dynamic-port-allocation     --min-ports-per-vm=64     --max-ports-per-vm=4096     --quiet
fi

"$REPO_ROOT/scripts/verify-fixlist-static-egress-canary.sh"
