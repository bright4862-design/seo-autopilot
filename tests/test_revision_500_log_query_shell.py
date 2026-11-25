"""Hermetic check: the operator's example passes a valid Cloud Logging filter."""
from pathlib import Path
import os
import subprocess


def test_revision_log_query_example_does_not_quote_literal_line_continuations(tmp_path):
    source = (
        Path(__file__).resolve().parents[1]
        / "scripts" / "summarize_revision_500_logs.py"
    ).read_text(encoding="utf-8")
    assert source.count("  gcloud logging read ") == 1
    sample = "gcloud logging read " + source.split(
        "  gcloud logging read ", 1
    )[1].split('\n\nUse "set -o pipefail"', 1)[0]
    assert '--query-limit 500' in sample
    capture = tmp_path / "captured_filter.txt"
    # Offline stand-ins. No gcloud, Cloud Logging, customer URL, or live call.
    shell = """set -euo pipefail
PROJECT=offline
gcloud() {
  test "$1" = "logging"
  test "$2" = "read"
  printf '%s' "$3" > "$FILTER_CAPTURE"
  printf '[]'
}
python() { cat >/dev/null; }
""" + sample
    ran = subprocess.run(
        ["bash", "-c", shell],
        env={**os.environ, "FILTER_CAPTURE": str(capture)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert ran.returncode == 0, "documented pipeline must parse under Bash"
    actual_filter = capture.read_text(encoding="utf-8")
    assert actual_filter.startswith('resource.type="cloud_run_revision" AND\n')
    assert "\\\n" not in actual_filter
    assert 'resource.labels.service_name="fixlist-standard150-worker"' in actual_filter
    assert 'resource.labels.revision_name="fixlist-standard150-worker-00097-lvl"' in actual_filter
    assert 'logName:"run.googleapis.com%2Frequests"' in actual_filter
    assert 'logName:"run.googleapis.com%2Fvarlog%2Fsystem"' in actual_filter
    assert 'severity>=ERROR' in actual_filter
    assert 'timestamp>="2026-11-23T12:06:50Z"' in actual_filter
    assert 'timestamp<="2026-11-23T12:09:35Z"' in actual_filter
