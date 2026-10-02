#!/usr/bin/env bash
set -euo pipefail

# One-time, human-run bootstrap for the Standard 150 one-IP static-egress canary.
# Run it from an authorized Cloud Shell on an exact, clean current-main checkout.
#
# The keyless GitHub operator never receives network-create rights. This script
# grants it one read-only custom role so the owner-only verify, stage and probe
# gates can inspect the canary resources, then runs the existing exact-main
# provisioner under the invoking administrator's own credentials. No key is
# created and no Owner, Editor, Compute Admin or Network Admin role is granted.

PROJECT="seo-autopilot-501517"
REGION="europe-west1"
SOURCE_SHA="${SOURCE_SHA:-}"
CONFIRM="${CONFIRM:-}"
OPERATOR_SA="fixlist-github-operator@${PROJECT}.iam.gserviceaccount.com"
VERIFIER_ROLE_ID="fixlistStaticEgressVerifier"
VERIFIER_ROLE="projects/${PROJECT}/roles/${VERIFIER_ROLE_ID}"
# Exactly the reads behind verify-fixlist-static-egress-canary.sh and the
# provisioner's existence checks: networks, subnets, addresses and routers
# describe. `routers nats describe` is a routers.get.
VERIFIER_PERMISSIONS="compute.addresses.get,compute.networks.get,compute.routers.get,compute.subnetworks.get"

# The canary contract names are fixed; a stray shell override must not
# provision differently named resources than the operator gates verify.
unset FIXLIST_EGRESS_NETWORK FIXLIST_EGRESS_SUBNET FIXLIST_EGRESS_SUBNET_CIDR \
  FIXLIST_EGRESS_ROUTER FIXLIST_EGRESS_NAT FIXLIST_EGRESS_ADDRESS

if [[ ! "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Refusing: SOURCE_SHA must be the exact 40-character current main SHA." >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO_ROOT/scripts/lib/release-source-guard.sh"
fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$SOURCE_SHA"

if [[ "$CONFIRM" != "BOOTSTRAP-STATIC-EGRESS-CANARY:$SOURCE_SHA" ]]; then
  echo "Refusing: CONFIRM must equal BOOTSTRAP-STATIC-EGRESS-CANARY:$SOURCE_SHA" >&2
  exit 2
fi

say() { printf '\n==> %s\n' "$*"; }

gcloud config set project "$PROJECT" >/dev/null

say "Refuse if the operator already holds a broad role"
for ROLE in roles/owner roles/editor roles/compute.admin roles/compute.networkAdmin; do
  FOUND="$(gcloud projects get-iam-policy "$PROJECT" \
    --flatten='bindings[].members' \
    --filter="bindings.role=${ROLE} AND bindings.members=serviceAccount:${OPERATOR_SA}" \
    --format='value(bindings.role)' | head -n 1)"
  if [[ -n "$FOUND" ]]; then
    echo "Refusing: operator holds prohibited broad role $ROLE; remove it before this bootstrap." >&2
    exit 4
  fi
done

say "Enable the Compute Engine API used by the canary network"
gcloud services enable compute.googleapis.com --project="$PROJECT" --quiet

say "Create or update the read-only static-egress verifier role"
if gcloud iam roles describe "$VERIFIER_ROLE_ID" --project="$PROJECT" >/dev/null 2>&1; then
  gcloud iam roles update "$VERIFIER_ROLE_ID" --project="$PROJECT" \
    --title="FixList static egress verifier" \
    --description="Read-only metadata for the static-egress canary network, subnet, address and router" \
    --permissions="$VERIFIER_PERMISSIONS" --stage=GA --quiet >/dev/null
else
  gcloud iam roles create "$VERIFIER_ROLE_ID" --project="$PROJECT" \
    --title="FixList static egress verifier" \
    --description="Read-only metadata for the static-egress canary network, subnet, address and router" \
    --permissions="$VERIFIER_PERMISSIONS" --stage=GA --quiet >/dev/null
fi

ROLE_JSON="$(mktemp)"
trap 'rm -f "$ROLE_JSON"' EXIT
gcloud iam roles describe "$VERIFIER_ROLE_ID" --project="$PROJECT" --format=json > "$ROLE_JSON"
python3 - "$ROLE_JSON" "$VERIFIER_PERMISSIONS" <<'PY'
import json, sys
role = json.load(open(sys.argv[1], encoding="utf-8"))
expected = sorted(sys.argv[2].split(","))
if sorted(role.get("includedPermissions") or []) != expected or role.get("deleted"):
    raise SystemExit("Refusing: static-egress verifier role is not exactly the read-only contract")
PY

say "Grant the operator only the read-only verifier role"
# Networks, addresses and routers have no resource-level IAM, so this
# metadata-only role is bound at the project.
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${OPERATOR_SA}" \
  --role="$VERIFIER_ROLE" \
  --condition=None \
  --quiet >/dev/null

say "Provision and verify the one-IP canary under this administrator's credentials"
SOURCE_SHA="$SOURCE_SHA" \
CONFIRM="STATIC-EGRESS-CANARY:$SOURCE_SHA" \
GCP_PROJECT="$PROJECT" \
GCP_REGION="$REGION" \
  bash "$REPO_ROOT/scripts/provision-fixlist-static-egress-canary.sh"

printf '\nSTATIC_EGRESS_BOOTSTRAP_COMPLETE\n'
printf 'source_sha=%s\n' "$SOURCE_SHA"
printf 'operator=%s role=%s\n' "$OPERATOR_SA" "$VERIFIER_ROLE"
printf 'No worker was staged, no traffic moved and no service-account key was created.\n'
printf 'Next: owner comment /provision-static-egress-canary %s (WIF read-only re-verification).\n' "$SOURCE_SHA"
