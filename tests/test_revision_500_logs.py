"""Offline P0 #378 falsifiers for the sanitized /revision 500 log reducer."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/summarize_revision_500_logs.py"
spec = importlib.util.spec_from_file_location("revision_logs", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
SERVICE = "fixlist-standard150-worker"
REVISION = "fixlist-standard150-worker-00097-lvl"
T0 = "2026-11-23T12:06:50Z"
T1 = "2026-11-23T12:09:35Z"


def row(status=500, *, timestamp="2026-11-23T12:07:12Z", trace="projects/test/traces/abc",
        revision=REVISION, path="/revision", ident="req1"):
    return {
        "resource": {"type": "cloud_run_revision", "labels": {"service_name": SERVICE, "revision_name": revision}},
        "timestamp": timestamp,
        "logName": "projects/test/logs/run.googleapis.com%2Frequests",
        "insertId": ident,
        "httpRequest": {"requestUrl": "https://private.example" + path, "status": status},
        "trace": trace,
        "jsonPayload": {"token": "must-never-print", "customer_url": "https://private-customer.test/"},
    }


def error(*, trace="projects/test/traces/abc", revision=REVISION, severity="ERROR"):
    x = row(revision=revision)
    x.pop("httpRequest")
    x.update({"trace": trace, "severity": severity,
              "logName": "projects/test/logs/run.googleapis.com%2Fstderr",
              "textPayload": "Traceback: Secret=never-print; internalURL=https://private-customer.test"})
    return x


def run(rows):
    return mod.summarize(rows, service=SERVICE, revision=REVISION, since=T0, until=T1)


def test_correlated_error_flag_not_causation():
    result = run([row(), error()])
    assert result["request_500_count"] == 1
    assert result["error_correlated_500_count"] == 1
    assert result["status"] == "METADATA_ONLY_DIAGNOSTIC_NOT_CAUSE_PROOF"
    assert "caused" not in result["interpretation"]


def test_without_error_trace_cause_remains_unknown():
    result = run([row()])
    assert result["request_500_count"] == 1
    assert result["error_correlated_500_count"] == 0


def test_wrong_trace_does_not_correlate():
    assert run([row(), error(trace="projects/test/traces/other")])["error_correlated_500_count"] == 0


def test_only_exact_revision_service_and_route():
    foreign_service = row(ident="other-service")
    foreign_service["resource"]["labels"]["service_name"] = "different-service"
    out = run([row(revision="fixlist-standard150-worker-00096-old", ident="old"),
               row(path="/revision-extra", ident="other-path"),
               row(path="/revision?token=secret", ident="valid-query"),
               foreign_service])
    assert out["request_500_count"] == 1
    assert len(out["requests"]) == 1


def test_timestamp_filter_and_duplicate_insert_id():
    out = run([row(), row(), row(ident="prior", timestamp="2026-11-23T11:00:00Z")])
    assert len(out["requests"]) == 1


def test_200_is_control_not_failure():
    out = run([row(status=200), error()])
    assert out["request_500_count"] == 0
    assert out["request_200_count"] == 1


def test_no_requests_is_not_health_evidence():
    out = run([error()])
    assert out["request_500_count"] == 0
    assert out["request_200_count"] == 0
    assert "Missing requests do not establish health" in out["interpretation"]


def test_never_print_sensitive_values():
    result = json.dumps(run([row(), error()]))
    for secret in ["never-print", "private-customer", "projects/test/traces", "private.example"]:
        assert secret not in result


def test_reject_unbounded_window():
    with pytest.raises(ValueError, match="30 minutes"):
        mod.summarize([], service=SERVICE, revision=REVISION,
                      since=T0, until="2026-11-23T13:06:50Z")


def test_reject_wrong_revision_prefix():
    with pytest.raises(ValueError, match="service-prefixed"):
        mod.summarize([], service=SERVICE, revision="another-worker-1", since=T0, until=T1)


def test_cli_only_outputs_metadata():
    result = subprocess.run([sys.executable, str(SCRIPT), "--service", SERVICE, "--revision", REVISION,
                             "--since", T0, "--until", T1], input=json.dumps([row(), error()]),
                            text=True, capture_output=True, check=True)
    obj = json.loads(result.stdout)
    assert obj["request_500_count"] == 1
    assert "never-print" not in (result.stdout + result.stderr)


def test_cli_refuses_bad_json_without_echo():
    result = subprocess.run([sys.executable, str(SCRIPT), "--service", SERVICE, "--revision", REVISION,
                             "--since", T0, "--until", T1], input="[customer-secret\n",
                            text=True, capture_output=True)
    assert result.returncode == 2
    assert result.stderr.strip() == "LOG_DIAGNOSTIC_INPUT_REJECTED"
    assert "customer-secret" not in result.stderr
