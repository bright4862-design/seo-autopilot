"""Offline regression for exact-worker selection in the Cloud Operator dispatcher.

The workflow runs both read-only checks and mutating operations, so its revision
input remains optional. But it must never silently prefill a historical
revision: promotion and emergency rollback must receive an explicit target.
No GCP credentials, networks, queues, or scans are involved in these tests.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/fixlist-cloud-operator.yml"
OPERATOR = ROOT / "scripts/fixlist-cloud-operator.sh"


def _shell_function(name: str) -> str:
    source = OPERATOR.read_text(encoding="utf-8")
    marker = f"{name}() {{\n"
    assert source.count(marker) == 1
    start = source.index(marker)
    end = source.index("\n}\n", start) + 3
    return source[start:end]


def _target_check(target: str, confirmation: str) -> subprocess.CompletedProcess[str]:
    # Fake the one Cloud Run revision lookup; even positive controls are offline.
    program = "\n".join([
        "set -euo pipefail",
        "gcloud() { return 0; }",
        "GCP_REGION=test-region",
        "GCP_PROJECT=test-project",
        f"TARGET_REVISION='{target}'",
        f"CONFIRM='{confirmation}'",
        _shell_function("require_confirmation"),
        _shell_function("require_target_revision"),
        "require_target_revision",
    ])
    return subprocess.run(
        ["bash", "-c", program],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )


def test_workflow_dispatch_has_no_stale_worker_revision_default():
    source = WORKFLOW.read_text(encoding="utf-8")
    match = re.search(r"(?m)^      revision:\n(?P<body>(?:^        .*\n)+)", source)
    assert match is not None
    block = match.group("body")
    assert '        default: ""\n' in block
    # Status and barrier reads need no target; target-requiring operations
    # are rejected by the operator guard when a revision was not supplied.
    assert "        required: false\n" in block
    assert "fixlist-standard150-worker-00011-v7m" not in block


def test_missing_dispatch_revision_is_refused_before_cloud_lookup():
    result = _target_check("", "")
    assert result.returncode == 2
    assert "an exact revision name is required" in result.stderr


def test_explicit_revision_preserves_confirmation_guard():
    target = "fixlist-standard150-worker-00104-l79"
    good = _target_check(target, target)
    bad = _target_check(target, "different-revision")
    assert good.returncode == 0, good.stderr
    assert bad.returncode == 2
    assert "confirmation must be exactly" in bad.stderr
