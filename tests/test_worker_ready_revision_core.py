"""Offline falsifiers: an updated Cloud Run service template can mask an old Ready worker."""
import json
import subprocess
import sys
from pathlib import Path

CHECK = Path(__file__).resolve().parents[1] / "scripts/check_worker_ready_revision_core.py"
REVISION = "fixlist-standard150-worker-00055-abc"
IMAGE = "europe-west1-docker.pkg.dev/test/repo/worker:verified"
RUNTIME_SA = "runtime@test.iam.gserviceaccount.com"
INVOKER_SA = "invoker@test.iam.gserviceaccount.com"
SOURCE_SHA = "a" * 40
SECRET = "SCAN_EVIDENCE_SIGNING_KEY"


def doc():
    return {
        "metadata": {"name": REVISION},
        "spec": {
            "serviceAccountName": RUNTIME_SA,
            "timeoutSeconds": 480,
            "containerConcurrency": 1,
            "containers": [{
                "image": IMAGE,
                "env": [
                    {"name": "BASE44_APP_ID", "value": "6a498732ec779dfaaeab0e53"},
                    {"name": "BASE44_API_URL", "value": "https://base44.app"},
                    {"name": "TASKS_INVOKER_SERVICE_ACCOUNT", "value": INVOKER_SA},
                    {"name": "FIXLIST_WORKER_SOURCE_SHA", "value": SOURCE_SHA},
                    {"name": "GROK_PROXY_ENABLED", "value": "false"},
                    {"name": SECRET, "valueFrom": {"secretKeyRef": {"name": SECRET, "key": "1"}}},
                ],
            }],
        },
    }


def run(document):
    raw = document if isinstance(document, str) else json.dumps(document)
    return subprocess.run(
        [
            sys.executable, str(CHECK),
            "--revision", REVISION, "--image", IMAGE,
            "--runtime-sa", RUNTIME_SA, "--invoker-sa", INVOKER_SA,
            "--source-sha", SOURCE_SHA, "--signing-secret", SECRET,
            "--signing-version", "1",
        ],
        input=raw, text=True, capture_output=True, timeout=10,
    )


def test_exact_ready_revision_core_is_accepted():
    done = run(doc())
    assert done.returncode == 0, done.stderr
    assert "READY_REVISION_CORE_MATCH" in done.stdout


def test_old_ready_image_refused_even_when_desired_template_matches():
    old = doc()
    old["spec"]["containers"][0]["image"] = "other-image"
    assert run(old).returncode == 1


def test_old_ready_signer_refused_even_when_template_pins_new_version():
    old = doc()
    old["spec"]["containers"][0]["env"][-1]["valueFrom"]["secretKeyRef"]["key"] = "2"
    assert run(old).returncode == 1


def test_foreign_ready_source_and_runtime_identity_refused():
    for field, value in (
        ("serviceAccountName", "other@test.iam.gserviceaccount.com"),
        ("timeoutSeconds", 30),
        ("containerConcurrency", 80),
    ):
        old = doc()
        old["spec"][field] = value
        assert run(old).returncode == 1, field
    for index, value in ((2, "foreign-invoker"), (3, "b" * 40)):
        old = doc()
        old["spec"]["containers"][0]["env"][index]["value"] = value
        assert run(old).returncode == 1, index


def test_missing_duplicate_and_plaintext_signer_refused():
    for mutation in ("missing", "duplicate", "plaintext", "foreign"):
        old = doc()
        env = old["spec"]["containers"][0]["env"]
        if mutation == "missing":
            env.pop()
        elif mutation == "duplicate":
            env.append(env[-1].copy())
        elif mutation == "plaintext":
            env[-1] = {"name": SECRET, "value": "never-echo-this-key"}
        else:
            env[-1]["valueFrom"]["secretKeyRef"]["name"] = "foreign-signing-key"
        result = run(old)
        assert result.returncode == 1, mutation
        assert "never-echo-this-key" not in result.stderr


def test_foreign_or_ambiguous_revision_metadata_refused():
    other = doc()
    other["metadata"]["name"] = "other-ready-revision"
    assert run(other).returncode == 1
    raw = json.dumps(doc()).replace('"metadata": {', '"metadata": {}, "metadata": {', 1)
    assert run(raw).returncode == 1


def test_grok_and_container_ambiguity_refused():
    for value in ("true", "TRUE", ""):
        old = doc()
        old["spec"]["containers"][0]["env"][4]["value"] = value
        assert run(old).returncode == 1
    old = doc()
    old["spec"]["containers"].append({"image": IMAGE, "env": []})
    assert run(old).returncode == 1


def test_no_secret_or_env_values_revealed_on_errors():
    old = doc()
    old["spec"]["containers"][0]["env"][-1] = {"name": SECRET, "value": "DO-NOT-REVEAL"}
    result = run(old)
    assert result.returncode == 1
    assert "DO-NOT-REVEAL" not in (result.stdout + result.stderr)
