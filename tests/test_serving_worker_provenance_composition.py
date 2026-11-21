"""Offline cross-guard contract: select the serving revision BEFORE attributing its build.

Regression controls for incident #378's read-only diagnostics. These tests make
no Google Cloud requests, do not authenticate, and do not establish deployment
or customer acceptance.
"""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SERVICE = "fixlist-standard150-worker"
OLD = SERVICE + "-00011-v7m"
SERVING = SERVICE + "-00012-ab1"
LATEST = SERVICE + "-00013-bc2"
IMAGE_REPO = "europe-west1-docker.pkg.dev/example/prod/worker"
OLD_SHA, SERVING_SHA = "a" * 40, "b" * 40
OLD_DIGEST = "sha256:" + "a" * 64
SERVING_DIGEST = "sha256:" + "b" * 64


def load(path, module_name):
    spec = importlib.util.spec_from_file_location(module_name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


routes = load("scripts/resolve_serving_worker_revision.py", "serving_revision_integration")
provenance = load("scripts/verify_worker_build_provenance.py", "provenance_integration")


def service(traffic=None):
    return {
        "metadata": {"generation": 9},
        "status": {
            "observedGeneration": 9,
            "conditions": [{"type": "Ready", "status": "True"}],
            "latestReadyRevisionName": LATEST,
            "traffic": traffic if traffic is not None else [
                {"revisionName": SERVING, "percent": 100},
                {"revisionName": LATEST, "percent": 0, "tag": "staged"},
            ],
        },
    }


def revision(name=SERVING):
    return {
        "metadata": {
            "name": name,
            "labels": {"serving.knative.dev/service": SERVICE},
        },
        "spec": {"containers": [{"image": IMAGE_REPO + ":" + SERVING_SHA}]},
        "status": {
            "conditions": [{"type": "Ready", "status": "True"}],
            "imageDigest": IMAGE_REPO + "@" + SERVING_DIGEST,
        },
    }


def build(sha, digest, build_id):
    return {
        "id": build_id,
        "status": "SUCCESS",
        "substitutions": {"_RELEASE_SHA": sha},
        "results": {
            "images": [{"name": IMAGE_REPO + ":" + sha, "digest": digest}],
        },
    }


def attest(control_plane, worker, builds):
    selected = routes.resolve(control_plane, service_name=SERVICE)
    return selected, provenance.derive_source_sha(
        worker, builds, expected_revision=selected, expected_service=SERVICE
    )


def test_real_serving_revision_is_used_for_immutable_build_provenance():
    assert OLD != LATEST != SERVING
    selected, (source, build_id, digest_ref) = attest(
        service(), revision(),
        [build(OLD_SHA, OLD_DIGEST, "old"), build(SERVING_SHA, SERVING_DIGEST, "serving")],
    )
    assert (selected, source, build_id) == (SERVING, SERVING_SHA, "serving")
    assert digest_ref == IMAGE_REPO + "@" + SERVING_DIGEST


def test_historical_revision_cannot_borrow_serving_route_selection():
    with pytest.raises(provenance.ProvenanceUnavailable, match="revision_name_mismatch"):
        attest(service(), revision(name=OLD), [build(SERVING_SHA, SERVING_DIGEST, "serving")])


def test_serving_traffic_drift_is_visible_before_build_attribution():
    first = routes.resolve(service(), service_name=SERVICE)
    after = routes.resolve(
        service([{"revisionName": LATEST, "percent": 100}]), service_name=SERVICE
    )
    assert first == SERVING
    assert after == LATEST
    assert after != first


def test_split_traffic_must_not_select_a_worker_for_build_attribution():
    split = service([
        {"revisionName": SERVING, "percent": 60},
        {"revisionName": LATEST, "percent": 40},
    ])
    with pytest.raises(routes.ServingRevisionUnavailable, match="single_100"):
        attest(split, revision(), [build(SERVING_SHA, SERVING_DIGEST, "serving")])


def test_matching_source_label_from_wrong_image_digest_is_not_acceptable():
    with pytest.raises(provenance.ProvenanceUnavailable, match="no_successful"):
        attest(service(), revision(), [build(SERVING_SHA, OLD_DIGEST, "wrong-digest")])


def test_contradictory_optional_git_provenance_is_not_a_signed_source_proof():
    row = build(SERVING_SHA, SERVING_DIGEST, "contradictory")
    row["sourceProvenance"] = {"resolvedRepoSource": {"commitSha": OLD_SHA}}
    with pytest.raises(provenance.ProvenanceUnavailable, match="repo_commit_conflicts"):
        attest(service(), revision(), [row])
