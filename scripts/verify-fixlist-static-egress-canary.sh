#!/usr/bin/env bash
set -euo pipefail

PROJECT="${GCP_PROJECT:-seo-autopilot-501517}"
REGION="${GCP_REGION:-europe-west1}"
NETWORK="${FIXLIST_EGRESS_NETWORK:-fixlist-scanner-egress}"
SUBNET="${FIXLIST_EGRESS_SUBNET:-fixlist-scanner-egress-euw1}"
SUBNET_CIDR="${FIXLIST_EGRESS_SUBNET_CIDR:-10.210.0.0/26}"
ROUTER="${FIXLIST_EGRESS_ROUTER:-fixlist-scanner-egress-router}"
NAT="${FIXLIST_EGRESS_NAT:-fixlist-scanner-egress-nat-a}"
ADDRESS="${FIXLIST_EGRESS_ADDRESS:-fixlist-scanner-egress-ip-a}"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

gcloud compute networks describe "$NETWORK" --project="$PROJECT" --format=json > "$tmp/network.json"
gcloud compute networks subnets describe "$SUBNET" --project="$PROJECT" --region="$REGION" --format=json > "$tmp/subnet.json"
gcloud compute addresses describe "$ADDRESS" --project="$PROJECT" --region="$REGION" --format=json > "$tmp/address.json"
gcloud compute routers describe "$ROUTER" --project="$PROJECT" --region="$REGION" --format=json > "$tmp/router.json"
gcloud compute routers nats describe "$NAT" --router="$ROUTER" --project="$PROJECT" --region="$REGION" --format=json > "$tmp/nat.json"

python3 - "$tmp" "$NETWORK" "$SUBNET" "$SUBNET_CIDR" "$REGION" "$ADDRESS" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
network, subnet, cidr, region, address_name = sys.argv[2:]

def load(name):
    return json.loads((root / name).read_text())

net = load("network.json")
sub = load("subnet.json")
addr = load("address.json")
router = load("router.json")
nat = load("nat.json")

if net.get("autoCreateSubnetworks") is not False:
    raise SystemExit("static egress network is not custom-mode")
if sub.get("ipCidrRange") != cidr or not str(sub.get("network") or "").endswith("/networks/" + network):
    raise SystemExit("static egress subnet contract mismatch")
if addr.get("addressType") != "EXTERNAL" or addr.get("networkTier") != "PREMIUM":
    raise SystemExit("static egress address contract mismatch")
if not str(addr.get("region") or "").endswith("/regions/" + region):
    raise SystemExit("static egress address region mismatch")
if not str(router.get("network") or "").endswith("/networks/" + network):
    raise SystemExit("static egress router network mismatch")
if nat.get("natIpAllocateOption") != "MANUAL_ONLY":
    raise SystemExit("static egress NAT is not manual-IP mode")
nat_ips = [str(x) for x in nat.get("natIps") or []]
if not any(x.endswith("/addresses/" + address_name) for x in nat_ips):
    raise SystemExit("static egress NAT does not use the reserved canary IP")
if nat.get("sourceSubnetworkIpRangesToNat") != "LIST_OF_SUBNETWORKS":
    raise SystemExit("static egress NAT is not subnet-scoped")
if nat.get("enableDynamicPortAllocation") is True:
    raise SystemExit("static egress NAT unexpectedly uses dynamic port allocation")
if int(nat.get("minPortsPerVm") or 0) != 256:
    raise SystemExit("static egress NAT minPortsPerVm differs from canary contract")
subnets = nat.get("subnetworks") or []
if len(subnets) != 1 or not str(subnets[0].get("name") or "").endswith("/subnetworks/" + subnet):
    raise SystemExit("static egress NAT subnet scope mismatch")
ranges = subnets[0].get("sourceIpRangesToNat") or []
if ranges != ["ALL_IP_RANGES"]:
    raise SystemExit("static egress NAT range contract mismatch")
ip = str(addr.get("address") or "")
parts = ip.split(".")
if len(parts) != 4 or any(not p.isdigit() or not 0 <= int(p) <= 255 for p in parts):
    raise SystemExit("static egress reserved IPv4 address missing")
print("STATIC_EGRESS_CANARY_READY=1")
print("STATIC_EGRESS_NETWORK=" + network)
print("STATIC_EGRESS_SUBNET=" + subnet)
print("STATIC_EGRESS_IP=" + ip)
PY
