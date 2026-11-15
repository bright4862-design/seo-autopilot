"""Fail-closed, secret-safe diagnostics for read-only staged infrastructure checks.

These are fake CLI responses, not evidence of live GCP resource state.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import verify_staged_scan_infra as verifier  # noqa: E402


@pytest.mark.parametrize("stderr, expected", [
    (
        "ERROR: (gcloud.storage.buckets.get-iam-policy) PERMISSION_DENIED: "
        "insufficient privilege; secret=do-not-echo",
        "ACCESS_DENIED_OR_HIDDEN",
    ),
    (
        "ERROR: (gcloud.tasks.queues.describe) NOT_FOUND: secret=do-not-echo",
        "NOT_FOUND_OR_INACCESSIBLE",
    ),
    (
        "ERROR: (gcloud.tasks.queues.describe) backend offline; secret=do-not-echo",
        "UNCLASSIFIED_GCLOUD_FAILURE",
    ),
    (None, "UNCLASSIFIED_GCLOUD_FAILURE"),
    (b"PERMISSION_DENIED secret=do-not-echo", "UNCLASSIFIED_GCLOUD_FAILURE"),
])
def test_failed_gcloud_read_is_typed_without_leaking_stderr(monkeypatch, stderr, expected):
    command = ["storage", "buckets", "get-iam-policy", "gs://private-example",
               "--project=seo-autopilot-501517"]
    def fake_run(argv, **kwargs):
        assert argv == ["gcloud", *command, "--format=json"]
        assert kwargs == {"check": True, "capture_output": True, "text": True}
        raise subprocess.CalledProcessError(1, argv, stderr=stderr)

    monkeypatch.setattr(verifier.subprocess, "run", fake_run)
    with pytest.raises(verifier.VerificationError) as error:
        verifier.describe(command)
    message = str(error.value)
    assert expected in message
    assert "staged resource and IAM state UNVERIFIED" in message
    assert message.startswith("storage buckets get-iam-policy:")
    assert "do-not-echo" not in message
    assert "private-example" not in message


def test_valid_gcloud_read_still_returns_json(monkeypatch):
    command = ["tasks", "queues", "describe", "fixlist-scan-stages"]
    def fake_run(argv, **kwargs):
        assert argv == ["gcloud", *command, "--format=json"]
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps({"state": "PAUSED"}), stderr="")

    monkeypatch.setattr(verifier.subprocess, "run", fake_run)
    assert verifier.describe(command) == {"state": "PAUSED"}
