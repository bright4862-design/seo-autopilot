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


NEW_REVISION = "fixlist-dispatch-gateway-g8a833143-20260912220236-a1b2c3"
OLD_REVISION = "fixlist-dispatch-gateway-00005-xt8"
# A revision another deployment created on the same service, concurrently.
FOREIGN_REVISION = "fixlist-dispatch-gateway-00015-def"
SERVICE_NAME = "fixlist-dispatch-gateway"
REVISION_SUFFIX = "g8a833143-20260912220236-a1b2c3"
SOURCE_SHA = "8a833143ef9ee9f8c7e4aa98399bec4b94b6193e"
CONTRACT_VERSION = "dispatch_gateway_robots_policy_diag_v1"
DIGEST = (
    "europe-west1-docker.pkg.dev/seo-autopilot-501517/cloud-run-source-deploy/"
    "fixlist-dispatch-gateway@sha256:8a14592667629f666ea5d435dea8c73080d499ae0bc086645ddcacd26804d41d"
)
QUEUE = "projects/seo-autopilot-501517/locations/europe-west1/queues/fixlist-standard150"
DRAIN_QUEUE = "projects/seo-autopilot-501517/locations/europe-west1/queues/fixlist-standard150-drain"
WORKER_ORIGIN = "https://fixlist-standard150-worker-tpucgyfewa-ew.a.run.app"


def service(serving=NEW_REVISION, percent=100, template_image=DIGEST, latest_created=None):
    return {
        "spec": {"template": {"spec": {"containers": [{"image": template_image}]}}},
        "status": {
            "traffic": [{"percent": percent, "revisionName": serving}],
            "latestCreatedRevisionName": latest_created or serving,
        },
    }


def revision(digest=DIGEST, source_sha=SOURCE_SHA, name=NEW_REVISION, ready="True", reason=None):
    return {
        "metadata": {"name": name},
        "status": {
            "imageDigest": digest,
            "conditions": [{"type": "Ready", "status": ready, "reason": reason}],
        },
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


# --- a concurrent deployment must not be mistaken for this one ---------------


def test_a_revision_created_by_another_deployment_is_never_promoted():
    # A second deploy lands between this one finishing and the service being
    # read back, so latestCreatedRevisionName -- and the traffic that second
    # deploy then took -- both name a revision this run never built. The gate
    # must refuse rather than attest the foreign revision.
    concurrent = service(serving=FOREIGN_REVISION, latest_created=FOREIGN_REVISION)
    assert concurrent["status"]["latestCreatedRevisionName"] == FOREIGN_REVISION
    with pytest.raises(verifier.VerificationError) as caught:
        verifier.verify_control_plane(concurrent, revision(), NEW_REVISION, SOURCE_SHA)
    assert FOREIGN_REVISION in str(caught.value)
    assert NEW_REVISION in str(caught.value)


def test_serving_revision_ignores_latest_created():
    # The newest revision on a service is not necessarily one this deployment
    # made. Only traffic decides, so a foreign latestCreatedRevisionName must
    # not change what this reads.
    assert (
        verifier.serving_revision(
            service(serving=NEW_REVISION, latest_created=FOREIGN_REVISION)
        )
        == NEW_REVISION
    )


def test_a_created_revision_under_a_foreign_name_is_refused():
    with pytest.raises(verifier.VerificationError) as caught:
        verifier.verify_created_revision(
            revision(name=FOREIGN_REVISION), NEW_REVISION, SOURCE_SHA
        )
    assert FOREIGN_REVISION in str(caught.value)
    assert "reserved" in str(caught.value)


def test_the_reserved_revision_is_accepted_once_ready():
    proven = verifier.verify_created_revision(revision(), NEW_REVISION, SOURCE_SHA)
    assert proven == {"created_revision": NEW_REVISION}


def test_a_reserved_revision_that_never_became_ready_is_refused():
    with pytest.raises(verifier.VerificationError) as caught:
        verifier.verify_created_revision(
            revision(ready="False", reason="ContainerHealthCheckFailed"),
            NEW_REVISION,
            SOURCE_SHA,
        )
    assert "not Ready" in str(caught.value)
    assert "ContainerHealthCheckFailed" in str(caught.value)


def test_a_reserved_revision_missing_its_ready_condition_is_refused():
    stale = revision()
    stale["status"]["conditions"] = []
    with pytest.raises(verifier.VerificationError):
        verifier.verify_created_revision(stale, NEW_REVISION, SOURCE_SHA)


def test_a_reserved_revision_built_from_another_commit_is_refused():
    with pytest.raises(verifier.VerificationError) as caught:
        verifier.verify_created_revision(
            revision(source_sha="7eaef7b98547e8f33a6c5674883fc970dcfa4a41"),
            NEW_REVISION,
            SOURCE_SHA,
        )
    assert "FIXLIST_GATEWAY_SOURCE_SHA" in str(caught.value)


# --- the revision name is decided before the deploy, not read back after -----


def test_planned_revision_is_the_service_name_joined_to_the_suffix():
    assert verifier.plan_revision(SERVICE_NAME, REVISION_SUFFIX) == NEW_REVISION


@pytest.mark.parametrize(
    "suffix",
    [
        "",
        "-leading-dash",
        "trailing-dash-",
        "Upper8a833143",
        "under_score",
        "has space",
        "a" * 64,
    ],
)
def test_planned_revision_refuses_a_suffix_cloud_run_would_reject(suffix):
    with pytest.raises(verifier.VerificationError):
        verifier.plan_revision(SERVICE_NAME, suffix)


def test_planned_revision_refuses_a_name_over_the_cloud_run_limit():
    with pytest.raises(verifier.VerificationError) as caught:
        verifier.plan_revision("a" * 40, REVISION_SUFFIX)
    assert "63" in str(caught.value)


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


def test_cli_plans_a_revision_without_reading_any_service_state(capsys):
    assert verifier.main([
        "--plan-revision",
        "--service", SERVICE_NAME,
        "--revision-suffix", REVISION_SUFFIX,
    ]) == 0
    assert capsys.readouterr().out == f"planned_revision={NEW_REVISION}\n"


def test_cli_exits_non_zero_for_an_unusable_revision_suffix(capsys):
    assert verifier.main([
        "--plan-revision",
        "--service", SERVICE_NAME,
        "--revision-suffix", "Not Valid",
    ]) == 2
    assert "Refusing gateway deployment" in capsys.readouterr().err


def test_cli_exits_non_zero_when_the_created_revision_is_foreign(tmp_path, capsys):
    code = verifier.main([
        "--created-revision-json",
        _write(tmp_path, "c.json", revision(name=FOREIGN_REVISION)),
        "--expected-revision", NEW_REVISION,
        "--expected-source-sha", SOURCE_SHA,
    ])
    assert code == 2
    assert FOREIGN_REVISION in capsys.readouterr().err


def test_cli_exits_non_zero_when_traffic_never_moved(tmp_path):
    code = verifier.main([
        "--service-json", _write(tmp_path, "s.json", service(serving=OLD_REVISION)),
        "--revision-json", _write(tmp_path, "r.json", revision()),
        "--expected-revision", NEW_REVISION,
        "--expected-source-sha", SOURCE_SHA,
    ])
    assert code == 2
