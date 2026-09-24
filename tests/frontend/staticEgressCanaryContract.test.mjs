import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const cloudbuild = readFileSync("cloudbuild.durable-worker.yaml", "utf8");
const build = readFileSync("scripts/build-worker-candidate.sh", "utf8");
const provision = readFileSync("scripts/provision-fixlist-static-egress-canary.sh", "utf8");
const verify = readFileSync("scripts/verify-fixlist-static-egress-canary.sh", "utf8");
const probe = readFileSync("scripts/verify-fixlist-static-egress-source-ip.sh", "utf8");
const operator = readFileSync("scripts/fixlist-cloud-operator.sh", "utf8");
const workflow = readFileSync(".github/workflows/fixlist-cloud-operator.yml", "utf8");

test("worker Cloud Build remains structurally singular after egress-mode extension", () => {
  assert.equal((cloudbuild.match(/id: deploy-private-worker/g) || []).length, 1);
  assert.equal((cloudbuild.match(/id: verify-release-source/g) || []).length, 1);
  assert.equal((cloudbuild.match(/logging: CLOUD_LOGGING_ONLY/g) || []).length, 1);
  assert.ok(cloudbuild.split("\n").length < 200, "worker Cloud Build unexpectedly duplicated");
});

test("static egress canary is one dedicated network, /24 subnet, and one manual NAT IP", () => {
  assert.match(provision, /fixlist-scanner-egress/);
  assert.match(provision, /fixlist-scanner-egress-euw1/);
  assert.match(provision, /10\.210\.0\.0\/24/);
  assert.match(provision, /fixlist-scanner-egress-ip-a/);
  assert.match(provision, /--nat-custom-subnet-ip-ranges="\$SUBNET:ALL"/);
  assert.match(provision, /--nat-external-ip-pool="\$ADDRESS"/);
  assert.match(verify, /natIpAllocateOption/);
  assert.match(verify, /MANUAL_ONLY/);
  assert.match(verify, /LIST_OF_SUBNETWORKS/);
  assert.doesNotMatch(provision, /add-iam-policy-binding|set-iam-policy|roles\/compute\.networkUser/);
});

test("normal worker builds explicitly clear Direct VPC while canary builds route all traffic through exact network", () => {
  assert.match(cloudbuild, /_EGRESS_MODE: "none"/);
  assert.match(cloudbuild, /none\)[\s\S]*deploy_args\+\=\(--clear-network\)/);
  assert.match(
    cloudbuild,
    /static-canary\)[\s\S]*--network=\$\{_EGRESS_NETWORK\}[\s\S]*--subnet=\$\{_EGRESS_SUBNET\}[\s\S]*--vpc-egress=all-traffic/,
  );
  assert.match(build, /FIXLIST_EGRESS_MODE:-none/);
  assert.match(build, /unexpected static-egress canary network/);
  assert.match(build, /unexpected static-egress canary subnet/);
});

test("candidate selection and verification bind source SHA to egress mode and Direct VPC annotations", () => {
  assert.match(build, /FIXLIST_WORKER_SOURCE_SHA/);
  assert.match(build, /FIXLIST_EGRESS_MODE/);
  assert.match(build, /run\.googleapis\.com\/network-interfaces/);
  assert.match(build, /run\.googleapis\.com\/vpc-access-egress/);
  assert.match(build, /candidate unexpectedly uses Direct VPC/);
  assert.match(build, /candidate VPC egress is not all-traffic/);
});

test("ordinary worker promotion refuses Direct VPC candidates until a dedicated accepted-egress gate exists", () => {
  assert.match(operator, /refuse_unaccepted_direct_vpc_promotion/);
  assert.match(operator, /Direct-VPC\/static-egress candidates require a dedicated accepted-egress promotion gate/);
  assert.match(operator, /promote_revision\(\)[\s\S]*refuse_unaccepted_direct_vpc_promotion "\$TARGET_REVISION"/);
});

test("owner-only workflow separates provision, stage, and source-IP verification with no promotion command", () => {
  assert.match(workflow, /\/provision-static-egress-canary /);
  assert.match(workflow, /\/stage-static-egress-worker /);
  assert.match(workflow, /\/verify-static-egress-source-ip /);
  assert.match(workflow, /FIXLIST_EGRESS_MODE: static-canary/);
  assert.match(workflow, /fixlist\/static-egress-candidate-stage/);
  assert.match(workflow, /fixlist\/static-egress-source-ip/);
  assert.doesNotMatch(workflow, /\/promote-static-egress-worker /);
});

test("source IP probe is bound to zero-traffic candidate revision and reserved NAT address", () => {
  assert.match(probe, /STATIC-EGRESS-PROBE:\$TARGET_REVISION:\$SOURCE_SHA/);
  assert.match(probe, /candidate unexpectedly serves customer traffic/);
  assert.match(probe, /api\.ipify\.org/);
  assert.match(probe, /STATIC_EGRESS_SOURCE_IP_VERIFIED=1/);
  assert.match(probe, /observed.*EXPECTED_IP|EXPECTED_IP.*observed/s);
});
