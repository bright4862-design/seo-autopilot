"""Offline exact-source tests for Standard 150 promotion rollback preflight.

The owner-comment workflow's existing rollback function restores one revision
to 100%. Preflight must not approve that mutation when the preexisting live
traffic is split, incomplete or insufficiently identified. This executes only
the extracted Python discovery code against synthetic Cloud Run JSON; there
are no cloud calls, credentials or customer scans.
"""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/fixlist-cloud-operator.yml"
SOURCE_SHA = "a" * 40
CANDIDATE = "fixlist-standard150-worker-00125-abc"
PRIOR = "worker-00100-prior"
DIGEST = "sha256:" + "1" * 64
IMAGE_REF = "europe-west1-docker.pkg.dev/example/worker@"+ DIGEST



def discovery_python() -> str:
    source = WORKFLOW.read_text(encoding="utf-8")
    begin = (
        '          readarray -t resolved < <(python3 - "$SOURCE_SHA" '
        '"$APPROVED_REVISION" "$APPROVED_IMAGE_DIGEST" '
        "/tmp/revisions.json /tmp/service-before.json <<'PY'\n"
    )
    end = "\n          PY\n"
    assert source.count(begin) == 1
    body = source.split(begin, 1)[1].split(end, 1)[0]
    assert "rollback = live[0][1]" in body
    return textwrap.dedent(body) + "\n"


def resolve(tmp_path: Path, traffic: list[dict], *, desired=None,
            generation=7, observed=7, ready="True", approved_revision=CANDIDATE,
            approved_digest=DIGEST, revision_digest=IMAGE_REF, extra_revisions=None):
    if desired is None:
        desired = [{"revisionName": PRIOR, "percent": 100}]
    revisions = [{
        "metadata": {"name": CANDIDATE, "creationTimestamp": "2026-11-13T00:00:00Z"},
        "spec": {
            "containers": [{"env": [
                {"name": "FIXLIST_WORKER_SOURCE_SHA", "value": SOURCE_SHA}
            ]}],
            "containerConcurrency": 1,
            "timeoutSeconds": 480,
        },
        "status": {"conditions": [{"type": "Ready", "status": "True"}],
                   "imageDigest": revision_digest},
    }]
    if extra_revisions:
        revisions.extend(extra_revisions)
    revisions_path = tmp_path / "revisions.json"
    service_path = tmp_path / "service.json"
    revisions_path.write_text(json.dumps(revisions), encoding="utf-8")
    service = {
        "metadata": {"generation": generation},
        "spec": {"traffic": desired},
        "status": {
            "observedGeneration": observed,
            "conditions": [{"type": "Ready", "status": ready}],
            "traffic": traffic,
        },
    }
    service_path.write_text(json.dumps(service), encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-c", discovery_python(), SOURCE_SHA,
         approved_revision, approved_digest, str(revisions_path), str(service_path)],
        capture_output=True, text=True, check=False, timeout=8,
    )


@pytest.mark.parametrize("traffic", [
    [{"revisionName": PRIOR, "percent": 100}],
    [{"revisionName": PRIOR, "percent": 100},
     {"revisionName": CANDIDATE, "percent": 0, "tag": "staging"}],
    [{"revisionName": PRIOR, "percent": "100"},
     {"revisionName": "ignored-tag", "percent": 0}],
])
def test_one_named_100_percent_rollback_is_preserved(tmp_path, traffic):
    result = resolve(tmp_path, traffic)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines() == [CANDIDATE, PRIOR]


@pytest.mark.parametrize("traffic", [
    [{"revisionName": PRIOR, "percent": 60},
     {"revisionName": "worker-another", "percent": 40}],
    [{"revisionName": PRIOR, "percent": 50},
     {"revisionName": PRIOR, "percent": 50}],
    [{"revisionName": PRIOR, "percent": 80}, {"percent": 20}],
    [{"revisionName": PRIOR, "percent": 99}],
    [{"revisionName": PRIOR, "percent": 100},
     {"revisionName": "unexpected", "percent": 1}],
    [{"revisionName": PRIOR, "percent": 100},
     {"revisionName": "invalid", "percent": -1}],
    [{"percent": 100}],
    [],
])
def test_lossy_or_ambiguous_rollback_preflight_is_refused(tmp_path, traffic):
    result = resolve(tmp_path, traffic)
    assert result.returncode != 0
    assert "Rollback preflight requires one named revision at exactly 100% traffic" in result.stderr
    assert result.stdout.strip() == ""


def test_candidate_already_live_still_refused(tmp_path):
    result = resolve(tmp_path, [{"revisionName": CANDIDATE, "percent": 100}])
    assert result.returncode != 0
    assert "Candidate already receives 100% traffic" in result.stderr


def test_preflight_is_before_first_candidate_tag_mutation():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert source.index("Rollback preflight requires one named revision at exactly 100% traffic") < (
        source.index("      - name: Tag the exact zero-traffic candidate")
    )


@pytest.mark.parametrize("kwargs,expected", [
    ({"generation": 8, "observed": 7}, "reconciled Ready"),
    ({"generation": 7, "observed": 8}, "reconciled Ready"),
    ({"generation": None}, "reconciled Ready"),
    ({"observed": None}, "reconciled Ready"),
    ({"ready": "Unknown"}, "reconciled Ready"),
    ({"ready": "False"}, "reconciled Ready"),
    ({"desired": [{"revisionName": "worker-other", "percent": 100}]}, "exact pinned"),
    ({"desired": [{"revisionName": PRIOR, "percent": 60},
                  {"revisionName": "worker-other", "percent": 40}]}, "exact pinned"),
    ({"desired": [{"latestRevision": True, "percent": 100}]}, "exact pinned"),
    ({"desired": [{"revisionName": PRIOR, "percent": True}]}, "exact pinned"),
    ({"desired": []}, "exact pinned"),
])
def test_observed_100_percent_is_not_sufficient(tmp_path, kwargs, expected):
    # The v1 status may still report old 100%-serving traffic while
    # metadata/spec already describe a different or incomplete desired state.
    result = resolve(tmp_path, [{"revisionName": PRIOR, "percent": 100}], **kwargs)
    assert result.returncode != 0
    assert expected in result.stderr
    assert result.stdout.strip() == ""


def test_exact_pinned_100_percent_with_zero_percent_tag_is_allowed(tmp_path):
    desired = [
        {"revisionName": PRIOR, "percent": 100},
        {"revisionName": CANDIDATE, "percent": 0, "tag": "candidate"},
    ]
    observed = [
        {"revisionName": PRIOR, "percent": 100},
        {"revisionName": CANDIDATE, "percent": 0, "tag": "candidate"},
    ]
    result = resolve(tmp_path, observed, desired=desired)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines() == [CANDIDATE, PRIOR]


def test_preflight_checks_desired_and_generation_before_first_tag():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    tag = workflow.index("      - name: Tag the exact zero-traffic candidate")
    assert workflow.index("Rollback preflight requires reconciled Ready Cloud Run service") < tag
    assert workflow.index("Rollback preflight requires exact pinned desired traffic") < tag


def test_approved_digest_selects_reviewed_revision_not_newest_matching_sha(tmp_path):
    # Regression: SHA-only timestamp selection silently picked this newer image.
    newer = {
        "metadata": {"name": "fixlist-standard150-worker-00126-def",
                     "creationTimestamp": "2026-11-23T04:30:00Z"},
        "spec": {"containers": [{"env": [
            {"name": "FIXLIST_WORKER_SOURCE_SHA", "value": SOURCE_SHA}]}],
                 "containerConcurrency": 1, "timeoutSeconds": 480},
        "status": {"conditions": [{"type": "Ready", "status": "True"}],
                   "imageDigest": "europe-west1-docker.pkg.dev/example/worker@sha256:" + "2" * 64},
    }
    result = resolve(tmp_path, [{"revisionName": PRIOR, "percent": 100}],
                     extra_revisions=[newer])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines() == [CANDIDATE, PRIOR]


@pytest.mark.parametrize("changes,diagnostic", [
    ({"approved_digest": "sha256:" + "2" * 64}, "image digest differs"),
    ({"revision_digest": "europe-west1-docker.pkg.dev/example/worker:latest"},
     "image digest differs"),
    ({"revision_digest": ""}, "image digest differs"),
    ({"approved_revision": "fixlist-standard150-worker-99999-zzz"},
     "Exactly one owner-approved worker revision"),
])
def test_digest_or_approved_revision_mismatch_fails_before_tag(tmp_path, changes, diagnostic):
    result = resolve(tmp_path, [{"revisionName": PRIOR, "percent": 100}], **changes)
    assert result.returncode != 0
    assert diagnostic in result.stderr
    assert result.stdout.strip() == ""


def test_owner_command_requires_exact_revision_and_digest():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    command = workflow.split(
        "      - name: Validate exact owner command and resolve product SHA", 1
    )[1].split("      - name: Authenticate to Google Cloud", 1)[0]
    assert 'approved_revision="${approval[2]}"' in command
    assert 'approved_image_digest="${approval[3]}"' in command
    assert 'approved_barrier_generation="${approval[4]}"' in command
    assert 'echo "barrier_generation=$approved_barrier_generation" >> "$GITHUB_OUTPUT"' in command
    assert 'echo "approved_revision=$approved_revision" >> "$GITHUB_OUTPUT"' in command
    assert "owner approval requires canonical revision, immutable image digest and exact closed-barrier generation" in command
    selection = workflow.split(
        "      - name: Discover exact zero-traffic candidate and rollback revision", 1
    )[1].split("      - name: Verify candidate build provenance and durable worker routes", 1)[0]
    assert 'APPROVED_REVISION: ${{ steps.command.outputs.approved_revision }}' in selection
    assert 'APPROVED_IMAGE_DIGEST: ${{ steps.command.outputs.approved_image_digest }}' in selection
    assert "Candidate image digest differs from owner-approved staged build" in selection
    assert "matches.sort" not in selection


def owner_command_bash() -> str:
    source = WORKFLOW.read_text(encoding="utf-8")
    step = source.split(
        "      - name: Validate exact owner command and resolve product SHA", 1
    )[1].split("      - name: Authenticate to Google Cloud", 1)[0]
    return textwrap.dedent(step.split("        run: |\n", 1)[1])


@pytest.mark.parametrize("mutate", [
    lambda cmd: cmd.rsplit(" ", 1)[0],
    lambda cmd: cmd.replace(DIGEST, "sha256:" + "x" * 64),
    lambda cmd: cmd.replace(CANDIDATE, "worker-another"),
    lambda cmd: cmd.replace(SOURCE_SHA, "b" * 40),
    lambda cmd: cmd + "  ",
    lambda cmd: cmd.replace(" 7", " 0"),
    lambda cmd: cmd.replace(" 7", " x"),
    lambda cmd: cmd.replace(" 7", " 8 7"),
])
def test_real_owner_command_rejects_missing_or_ambiguous_digest_before_cloud(tmp_path, mutate):
    result, output = run_owner_command(tmp_path, mutate(owner_approval()))
    assert result.returncode != 0
    assert output == ""


def owner_approval() -> str:
    return f"/promote-staged-worker {SOURCE_SHA} {CANDIDATE} {DIGEST} 7"


def run_owner_command(tmp_path: Path, comment: str):
    import os

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_git = fake_bin / "git"
    fake_git.write_text(f"#!/bin/sh\nprintf '%s\\n' '{SOURCE_SHA}'\n", encoding="utf-8")
    fake_git.chmod(0o755)
    output = tmp_path / "workflow-output"
    output.write_text("", encoding="utf-8")
    env = {**os.environ, "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"],
           "COMMENT_BODY": comment, "COMMENT_USER": "bright4862-design",
           "GITHUB_REF": "refs/heads/main", "GITHUB_SHA": SOURCE_SHA,
           "GITHUB_OUTPUT": str(output)}
    result = subprocess.run(["bash", "-c", owner_command_bash()], env=env,
                            capture_output=True, text=True, timeout=5)
    return result, output.read_text(encoding="utf-8")


def test_real_owner_command_accepts_only_exact_reviewed_revision_and_digest(tmp_path):
    result, output = run_owner_command(tmp_path, owner_approval())
    assert result.returncode == 0, result.stderr
    assert "source_sha=" + SOURCE_SHA in output
    assert "approved_revision=" + CANDIDATE in output
    assert "approved_image_digest=" + DIGEST in output
    assert "barrier_generation=7" in output


def signed_barrier_preflight_bash() -> str:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    name = "      - name: Verify signed closed and drained barrier before promotion"
    nxt = "      - name: Restore keyless worker operator credentials for promotion"
    assert workflow.count(name) == 1 and workflow.count(nxt) == 1
    step = workflow.split(name, 1)[1].split(nxt, 1)[0]
    return textwrap.dedent(step.split("        run: |\n", 1)[1])


def test_closed_drained_barrier_preflight_is_before_first_traffic_promotion():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    begin = workflow.index("  promote-staged-worker-on-owner-comment:")
    end = workflow.index("  readonly-diagnostic:", begin)
    section = workflow[begin:end]
    assert section.index("Verify matching Base44 site and executing scanner/customer routes") < (
        section.index("Verify signed closed and drained barrier before promotion"))
    assert section.index("Verify signed closed and drained barrier before promotion") < (
        section.index("Promote exact candidate with automatic rollback on failed post-check"))
    assert "OPERATION: verify-zero-admission-obligations" in section
    assert "GCP_ADMISSION_OPERATOR_SERVICE_ACCOUNT" in section
    assert "BARRIER_EXPECTED_GENERATION: ${{ steps.command.outputs.barrier_generation }}" in section
    assert "Restore keyless worker operator credentials for promotion" in section


@pytest.mark.parametrize("verdict,rc,allowed", [
    ("ADMISSION_ZERO_OBLIGATIONS_VERIFIED generation=7 snapshot=signed-abc expired_diagnostic=0", 0, True),
    ("ADMISSION_ZERO_OBLIGATIONS_VERIFIED generation=8 snapshot=signed-abc expired_diagnostic=0", 0, False),
    ("ADMISSION_BARRIER_STATUS mode=open generation=7", 0, False),
    ("ADMISSION_ZERO_OBLIGATIONS_VERIFIED generation=7 snapshot=signed-abc expired_diagnostic=0", 7, False),
    ("", 0, False),
])
def test_real_promotion_barrier_bash_fails_closed(tmp_path, verdict, rc, allowed):
    # Hermetic gate rehearsal: the existing coordinator verifier authenticates
    # HMAC/counters; this tests only how the promotion step consumes its verdict.
    import os

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_bash = fake_bin / "bash"
    fake_bash.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$FAKE_BARRIER_VERDICT\"\nexit \"$FAKE_BARRIER_RC\"\n",
        encoding="utf-8",
    )
    fake_bash.chmod(0o755)
    env = {**os.environ,
           "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"],
           "FAKE_BARRIER_VERDICT": verdict, "FAKE_BARRIER_RC": str(rc),
           "BARRIER_EXPECTED_GENERATION": "7"}
    proc = subprocess.run(["/bin/bash", "-c", signed_barrier_preflight_bash()],
                          env=env, capture_output=True, text=True, timeout=5)
    assert (proc.returncode == 0) is allowed, (proc.stdout, proc.stderr)
