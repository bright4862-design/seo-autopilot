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

def test_info_system_logs_are_not_silently_dropped():
    """Cloud Run instance-start INFO records can lack request trace."""
    system = error(trace="")
    system["severity"] = "INFO"
    system["logName"] = "projects/test/logs/run.googleapis.com%2Fvarlog%2Fsystem"
    system["textPayload"] = "Starting new instance. Sensitive: never-print"
    out = run([row(), system])
    assert out["request_500_count"] == 1
    assert out["system_log_count"] == 1
    assert out["system_error_log_count"] == 0
    assert "never-print" not in json.dumps(out)
    assert 'logName:"run.googleapis.com%2Fvarlog%2Fsystem"' in mod.__doc__


def test_untraced_stderr_is_distinguished_from_absent_error_logs():
    out = run([row(), error(trace="")])
    assert out["error_correlated_500_count"] == 0
    assert out["untraced_nonrequest_error_count"] == 1
    assert "uncorrelated" in out["interpretation"]


def test_system_error_count_does_not_claim_request_causation():
    system = error(trace="", severity="ERROR")
    system["logName"] = "projects/test/logs/run.googleapis.com%2Fvarlog%2Fsystem"
    out = run([row(trace="different-trace"), system])
    assert out["system_log_count"] == 1
    assert out["system_error_log_count"] == 1
    assert out["error_correlated_500_count"] == 0
    assert out["untraced_nonrequest_error_count"] == 1


def test_limit_saturation_fail_closed_without_exposing_log_payloads():
    # gcloud defaults to descending order. A 500-row limit can hide the old
    # failure even though it exists in the full 501-row matching set.
    filler = []
    for i in range(500):
        x = error(trace="", severity="INFO")
        x["logName"] = "projects/test/logs/run.googleapis.com%2Fvarlog%2Fsystem"
        x["timestamp"] = "2026-11-23T12:08:00Z"
        x["insertId"] = f"filler-{i}"
        x["textPayload"] = "SECRET_PII_NEVER_LOG"
        filler.append(x)
    older_failure = row(timestamp="2026-11-23T12:07:12Z", ident="older-failure")
    assert run(filler)["request_500_count"] == 0  # no request in first page
    saturated = run(filler)
    assert saturated["query_at_limit"] is True
    assert saturated["status"] == "INDETERMINATE_QUERY_AT_LIMIT"
    assert saturated["query_entry_count"] == 500
    assert "SECRET_PII_NEVER_LOG" not in json.dumps(saturated)
    assert run(filler + [older_failure])["request_500_count"] == 1


def test_limit_below_threshold_preserves_status_and_known_request():
    observed = run([row(), error(trace="")])
    assert observed["status"] == "METADATA_ONLY_DIAGNOSTIC_NOT_CAUSE_PROOF"
    assert observed["query_at_limit"] is False
    assert observed["query_entry_count"] == 2
    assert observed["query_limit"] == 500


def test_custom_limit_controls_saturation_and_is_strict():
    assert mod.summarize([row()], service=SERVICE, revision=REVISION,
                         since=T0, until=T1, query_limit=1)["query_at_limit"]
    with pytest.raises(ValueError, match="query limit"):
        mod.summarize([row()], service=SERVICE, revision=REVISION,
                      since=T0, until=T1, query_limit=True)
    with pytest.raises(ValueError, match="query limit"):
        mod.summarize([row()], service=SERVICE, revision=REVISION,
                      since=T0, until=T1, query_limit=1001)


def test_cli_exits_nonzero_with_sanitized_evidence_when_limit_reached():
    fixture = row()
    fixture["jsonPayload"]["token"] = "PRIVATE_SECRET"
    result = subprocess.run([sys.executable, str(SCRIPT), "--service", SERVICE, "--revision", REVISION,
                             "--since", T0, "--until", T1, "--query-limit", "1"],
                            input=json.dumps([fixture]), text=True, capture_output=True)
    assert result.returncode == 3
    assert json.loads(result.stdout)["status"] == "INDETERMINATE_QUERY_AT_LIMIT"
    assert "PRIVATE_SECRET" not in (result.stdout + result.stderr)


def test_reused_insert_id_on_distinct_timestamps_does_not_hide_a_500():
    """Cloud Logging insertId alone is not a global event identity."""
    first = row(status=200, ident="reused-id", timestamp="2026-11-23T12:07:12Z")
    second = row(status=500, ident="reused-id", timestamp="2026-11-23T12:09:12Z")
    out = run([first, second])
    assert out["request_200_count"] == 1
    assert out["request_500_count"] == 1
    assert [r["http_status"] for r in out["requests"]] == [200, 500]


def test_exact_timestamp_and_insert_id_are_still_deduplicated():
    """Repeated reads of one Cloud Logging entry stay one observation."""
    duplicate = row(ident="same-event", timestamp="2026-11-23T12:07:12.123456Z")
    out = run([duplicate, dict(duplicate)])
    assert out["request_500_count"] == 1


def test_distinct_insert_ids_at_same_timestamp_are_distinct():
    out = run([row(ident="first"), row(ident="second")])
    assert out["request_500_count"] == 2
