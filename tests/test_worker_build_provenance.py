"""Adversarial, offline controls for immutable Standard 150 build attribution."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_worker_build_provenance.py"
spec = importlib.util.spec_from_file_location("worker_build_provenance", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

REV = "fixlist-standard150-worker-00099-abc"
SERVICE = "fixlist-standard150-worker"
REPO = "europe-west1-docker.pkg.dev/example/prod/worker"
SHA_A, SHA_B = "a" * 40, "b" * 40
DIG_A, DIG_B = "sha256:" + "a" * 64, "sha256:" + "b" * 64


def revision(tag=True, digest=DIG_B):
    return {
        "metadata": {"name": REV, "labels": {"serving.knative.dev/service": SERVICE}},
        "spec": {"containers": [{"image": REPO + (":" + SHA_B if tag else "@" + DIG_B)}]},
        "status": {"conditions": [{"type": "Ready", "status": "True"}],
                   "imageDigest": REPO + "@" + digest},
    }


def build(sha, digest, *, status="SUCCESS", image_repo=REPO, build_id=None):
    return {
        "id": build_id or sha[:8], "status": status,
        "substitutions": {"_RELEASE_SHA": sha},
        "results": {"images": [{"name": image_repo + ":" + sha, "digest": digest}]},
    }


def check(rev=None, builds=None):
    return module.derive_source_sha(rev if rev is not None else revision(),
                                    builds if builds is not None else [build(SHA_A, DIG_A), build(SHA_B, DIG_B)],
                                    expected_revision=REV, expected_service=SERVICE)


def test_tag_must_not_override_resolved_digest():
    # Reconstruct exact old operator's selection predicate for the baseline.
    rows = [build(SHA_A, DIG_A), build(SHA_B, DIG_B)]
    image = revision()["spec"]["containers"][0]["image"]
    digest = image.rsplit("@", 1)[-1] if "@" in image else ""
    name = image.split("@")[0].split(":")[0]
    baseline = next(record["substitutions"]["_RELEASE_SHA"] for record in rows
                    if (digest and digest in [i["digest"] for i in record["results"]["images"]])
                    or (not digest and any(i["name"].split("@")[0].split(":")[0] == name
                                           for i in record["results"]["images"])))
    assert baseline == SHA_A, "tag-based first-match baseline misattributes source"
    assert check() == (SHA_B, SHA_B[:8], REPO + "@" + DIG_B)
    assert check(revision(tag=False))[0] == SHA_B


def test_same_digest_in_other_repository_is_not_provenance():
    with pytest.raises(module.ProvenanceUnavailable, match="no_successful"):
        check(builds=[build(SHA_A, DIG_B, image_repo=REPO + "-other")])


def test_unsuccessful_and_unstamped_builds_are_not_sources():
    for record in [build(SHA_B, DIG_B, status="FAILURE"),
                   {**build(SHA_B, DIG_B), "substitutions": {}},
                   {**build(SHA_B, DIG_B), "results": {"images": []}}]:
        with pytest.raises(module.ProvenanceUnavailable, match="no_successful"):
            check(builds=[record])


def test_duplicate_successful_builds_are_ambiguous_even_if_sha_matches():
    with pytest.raises(module.ProvenanceUnavailable, match="ambiguous"):
        check(builds=[build(SHA_B, DIG_B, build_id="build-one"),
                      build(SHA_B, DIG_B, build_id="build-two")])


@pytest.mark.parametrize("field,replace,error", [
    ("status", {"imageDigest": REPO + "@" + DIG_B}, "revision_not_ready"),
    ("status", {"imageDigest": REPO + ":" + SHA_B,
                "conditions": [{"type": "Ready", "status": "True"}]}, "resolved_image_digest_missing"),
    ("status", {"imageDigest": REPO + "-different@" + DIG_B,
                "conditions": [{"type": "Ready", "status": "True"}]}, "resolved_image_digest_mismatch"),
    ("metadata", {"name": REV, "labels": {"serving.knative.dev/service": "other"}}, "revision_service_mismatch"),
    ("metadata", {"name": "another", "labels": {"serving.knative.dev/service": SERVICE}}, "revision_name_mismatch"),
])
def test_invalid_revision_identity_fails(field, replace, error):
    rev = revision(); rev[field] = replace
    with pytest.raises(module.ProvenanceUnavailable, match=error):
        check(rev=rev)


def test_malformed_build_image_tag_does_not_match_digest():
    wrong = build(SHA_B, DIG_B)
    wrong["results"]["images"][0]["name"] = REPO + ":latest"
    with pytest.raises(module.ProvenanceUnavailable, match="no_successful"):
        check(builds=[wrong])


def test_build_record_window_exhaustion_fails_closed():
    with pytest.raises(module.ProvenanceUnavailable, match="no_successful"):
        check(builds=[build(SHA_A, DIG_A)])


def test_cli_is_read_only_and_returns_only_source_sha_on_stdout(tmp_path):
    path_revision = tmp_path / "revision.json"
    path_builds = tmp_path / "builds.json"
    path_revision.write_text(json.dumps(revision()))
    path_builds.write_text(json.dumps([build(SHA_A, DIG_A), build(SHA_B, DIG_B)]))
    command = [sys.executable, str(SCRIPT), "--revision-json", str(path_revision),
               "--builds-json", str(path_builds), "--revision", REV, "--service", SERVICE]
    run = subprocess.run(command, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert run.stdout == SHA_B + "\n"
    path_builds.write_text(json.dumps([build(SHA_A, DIG_A)]))
    run = subprocess.run(command, capture_output=True, text=True)
    assert run.returncode == 2
    assert not run.stdout
    assert "INDETERMINATE" in run.stderr


def test_unexpected_container_count_refused():
    rev = revision(); rev["spec"]["containers"].append({"image": REPO + ":latest"})
    with pytest.raises(module.ProvenanceUnavailable, match="container_ambiguous"):
        check(rev=rev)


def test_spec_digest_must_agree_with_resolved_digest():
    rev = revision(tag=False)
    rev["spec"]["containers"][0]["image"] = REPO + "@" + DIG_A
    with pytest.raises(module.ProvenanceUnavailable, match="image_spec_and_resolved_digest_disagree"):
        check(rev=rev)


def test_matching_build_missing_id_refuses_specific_attribution():
    matched = build(SHA_B, DIG_B)
    matched["id"] = ""
    with pytest.raises(module.ProvenanceUnavailable, match="matching_build_id_missing"):
        check(builds=[matched])


def test_duplicate_ready_conditions_do_not_prove_readiness():
    rev = revision()
    rev["status"]["conditions"].append({"type": "Ready", "status": "False"})
    with pytest.raises(module.ProvenanceUnavailable, match="revision_not_ready"):
        check(rev=rev)


def test_matching_build_cannot_override_contradictory_repo_provenance():
    matched = build(SHA_B, DIG_B)
    matched["sourceProvenance"] = {"resolvedRepoSource": {"commitSha": SHA_A}}
    with pytest.raises(module.ProvenanceUnavailable,
                       match="matching_build_repo_commit_conflicts_with_release_label"):
        check(builds=[matched])


def test_archive_storage_provenance_without_repo_sha_is_accepted():
    # The actual gcloud builds submit workflow uploads a local source archive;
    # resolvedStorageSource records its GCS object/generation, not a Git commit.
    matched = build(SHA_B, DIG_B)
    matched["sourceProvenance"] = {
        "resolvedStorageSource": {
            "bucket": "synthetic-build-source",
            "object": "source/archive.tgz",
            "generation": "12",
        }
    }
    assert check(builds=[matched])[0] == SHA_B


def test_matching_optional_repo_sha_does_not_block_legitimate_source():
    matched = build(SHA_B, DIG_B)
    matched["sourceProvenance"] = {"resolvedRepoSource": {"commitSha": SHA_B}}
    assert check(builds=[matched])[0] == SHA_B


@pytest.mark.parametrize("bad_provenance", ["not-json-object", {"resolvedRepoSource": "invalid"}])
def test_malformed_reported_provenance_is_indeterminate(bad_provenance):
    matched = build(SHA_B, DIG_B)
    matched["sourceProvenance"] = bad_provenance
    with pytest.raises(module.ProvenanceUnavailable, match="provenance_malformed|repo_source_malformed"):
        check(builds=[matched])
