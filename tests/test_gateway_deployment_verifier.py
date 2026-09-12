"""Behaviour coverage for the dispatch-gateway deployment verifier.

These are fixture-driven rather than source greps. The failure they exist to
catch is a deployment that looks correct at every layer except the one that
matters: the control plane says the new revision holds all traffic, the image
digest and environment match, and /health returns the expected source SHA and
contract version -- yet the response came from a different revision, because
the untagged service URL can still be answered by the revision being drained
while traffic propagates. Two revisions built from one commit are
indistinguishable by source SHA, so only the executing revision separates them.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "verify_gateway_deployment.py"
SPEC = importlib.util.spec_from_file_location("verify_gateway_deployment", MODULE_PATH)
assert SPEC and SPEC.loader
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


NEW_REVISION = "fixlist-dispatch-gateway-00014-abc"
OLD_REVISION = "fixlist-dispatch-gateway-00005-xt8"
SOURCE_SHA = "8a833143ef9ee9f8c7e4aa98399bec4b94b6193e"
CONTRACT_VERSION = "dispatch_gateway_robots_policy_diag_v1"
DIGEST = (
    "europe-west1-docker.pkg.dev/seo-autopilot-501517/cloud-run-source-deploy/"
    "fixlist-dispatch-gateway@sha256:8a14592667629f666ea5d435dea8c73080d499ae0bc086645ddcacd26804d41d"
)
QUEUE = "projects/seo-autopilot-501517/locations/europe-west1/queues/fixlist-standard150"
DRAIN_QUEUE = "projects/seo-autopilot-501517/locations/europe-west1/queues/fixlist-standard150-drain"
WORKER_ORIGIN = "https://fixlist-standard150-worker-tpucgyfewa-ew.a.run.app"


def service(serving=NEW_REVISION, percent=100, template_image=DIGEST):
    return {
        "spec": {"template": {"spec": {"containers": [{"image": template_image}]}}},
        "status": {"traffic": [{"percent": percent, "revisionName": serving}]},
    }


def revision(digest=DIGEST, source_sha=SOURCE_SHA):
    return {
        "status": {"imageDigest": digest},
        "spec": {
            "containers": [
                {"env": [{"name": "FIXLIST_GATEWAY_SOURCE_SHA", "value": source_sha}]}
            ]
        },
    }


def health(revision_name=NEW_REVISION, source_sha=SOURCE_SHA, **overrides):
    payload = {
        "ok": True,
        "service": "fixlist-dispatch-gateway",
        "contract_version": CONTRACT_VERSION,
        "source_sha": source_sha,
        "revision": revision_name,
        "queue": QUEUE,
        "drain_queue": DRAIN_QUEUE,
        "worker_origin": WORKER_ORIGIN,
    }
    payload.update(overrides)
    return payload


def check_health(payload, expected_revision=NEW_REVISION):
    return verifier.verify_runtime_health(
        payload,
        expected_revision,
        SOURCE_SHA,
        CONTRACT_VERSION,
        QUEUE,
        DRAIN_QUEUE,
        WORKER_ORIGIN,
    )


# --- the propagation false positive -----------------------------------------


def test_health_answered_by_the_draining_revision_is_refused():
    # Control plane is entirely correct and /health carries the right source
    # SHA and contract version, because the old revision was built from the
    # same commit. Only the executing revision differs.
    verifier.verify_control_plane(service(), revision(), NEW_REVISION, SOURCE_SHA)
    with pytest.raises(verifier.VerificationError) as caught:
        check_health(health(revision_name=OLD_REVISION))
    assert "revision" in str(caught.value)
    assert OLD_REVISION in str(caught.value)


def test_health_answered_by_the_promoted_revision_is_accepted():
    proven = check_health(health())
    assert proven == {
        "runtime_revision": NEW_REVISION,
        "runtime_source_sha": SOURCE_SHA,
    }


def test_health_without_a_revision_field_is_refused():
    # Bytes predating the revision field must not satisfy the contract.
    payload = health()
    del payload["revision"]
    with pytest.raises(verifier.VerificationError):
        check_health(payload)


# --- the four-week failure this whole gate exists for ------------------------


def test_traffic_still_on_the_previous_revision_is_refused():
    with pytest.raises(verifier.VerificationError) as caught:
        verifier.verify_control_plane(
            service(serving=OLD_REVISION), revision(), NEW_REVISION, SOURCE_SHA
        )
    assert OLD_REVISION in str(caught.value)


def test_partial_traffic_on_the_new_revision_is_refused():
    with pytest.raises(verifier.VerificationError) as caught:
        verifier.verify_control_plane(
            service(percent=50), revision(), NEW_REVISION, SOURCE_SHA
        )
    assert "50%" in str(caught.value)


def test_serving_digest_other_than_the_built_image_is_refused():
    other = DIGEST.replace("@sha256:8a14", "@sha256:dead")
    with pytest.raises(verifier.VerificationError):
        verifier.verify_control_plane(
            service(), revision(digest=other), NEW_REVISION, SOURCE_SHA
        )


def test_revision_without_an_immutable_digest_is_refused():
    with pytest.raises(verifier.VerificationError):
        verifier.verify_control_plane(
            service(template_image="fixlist-dispatch-gateway:latest"),
            revision(digest="fixlist-dispatch-gateway:latest"),
            NEW_REVISION,
            SOURCE_SHA,
        )


def test_serving_revision_carrying_a_foreign_source_sha_is_refused():
    # The August revision carried 7eaef7b9..., a commit absent from this repo.
    with pytest.raises(verifier.VerificationError) as caught:
        verifier.verify_control_plane(
            service(),
            revision(source_sha="7eaef7b98547e8f33a6c5674883fc970dcfa4a41"),
            NEW_REVISION,
            SOURCE_SHA,
        )
    assert "FIXLIST_GATEWAY_SOURCE_SHA" in str(caught.value)


def test_control_plane_reads_status_traffic_not_the_desired_template():
    # spec.template is the template the deploy just wrote, so it always agrees
    # with itself. Only status.traffic can disagree, and it must be believed.
    stale = service(serving=OLD_REVISION)
    assert verifier.serving_revision(stale) == OLD_REVISION


# --- old bytes must not satisfy the contract ---------------------------------


def test_health_missing_contract_version_is_refused():
    payload = health()
    del payload["contract_version"]
    with pytest.raises(verifier.VerificationError):
        check_health(payload)


def test_health_with_a_different_source_sha_is_refused():
    with pytest.raises(verifier.VerificationError):
        check_health(health(source_sha="7eaef7b98547e8f33a6c5674883fc970dcfa4a41"))


# --- process exit codes ------------------------------------------------------


def _write(tmp_path, name, payload):
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_cli_exits_non_zero_when_health_reports_the_wrong_revision(tmp_path, capsys):
    code = verifier.main([
        "--health-json", _write(tmp_path, "h.json", health(revision_name=OLD_REVISION)),
        "--expected-revision", NEW_REVISION,
        "--expected-source-sha", SOURCE_SHA,
        "--expected-contract-version", CONTRACT_VERSION,
        "--queue-path", QUEUE,
        "--drain-queue-path", DRAIN_QUEUE,
        "--worker-origin", WORKER_ORIGIN,
    ])
    assert code == 2
    assert "Refusing gateway deployment" in capsys.readouterr().err


def test_cli_exits_zero_on_a_genuine_deployment(tmp_path, capsys):
    control = verifier.main([
        "--service-json", _write(tmp_path, "s.json", service()),
        "--revision-json", _write(tmp_path, "r.json", revision()),
        "--expected-revision", NEW_REVISION,
        "--expected-source-sha", SOURCE_SHA,
    ])
    runtime = verifier.main([
        "--health-json", _write(tmp_path, "h.json", health()),
        "--expected-revision", NEW_REVISION,
        "--expected-source-sha", SOURCE_SHA,
        "--expected-contract-version", CONTRACT_VERSION,
        "--queue-path", QUEUE,
        "--drain-queue-path", DRAIN_QUEUE,
        "--worker-origin", WORKER_ORIGIN,
    ])
    assert (control, runtime) == (0, 0)
    assert f"runtime_revision={NEW_REVISION}" in capsys.readouterr().out


def test_cli_exits_non_zero_when_traffic_never_moved(tmp_path):
    code = verifier.main([
        "--service-json", _write(tmp_path, "s.json", service(serving=OLD_REVISION)),
        "--revision-json", _write(tmp_path, "r.json", revision()),
        "--expected-revision", NEW_REVISION,
        "--expected-source-sha", SOURCE_SHA,
    ])
    assert code == 2
