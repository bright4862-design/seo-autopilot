from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from scripts.standard150_acceptance_matrix import (  # noqa: E402
    REQUIRED_MATRIX_DIMENSIONS,
    _matrix_contract_gaps,
    build_acceptance_matrix,
)


SPEC = importlib.util.spec_from_file_location(
    "standard150_ramp_harness",
    SCRIPTS / "standard150-ramp-harness.py",
)
assert SPEC and SPEC.loader
HARNESS = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = HARNESS
SPEC.loader.exec_module(HARNESS)


def test_ramp_acceptance_targets_the_browser_v8_routes_not_legacy_aliases():
    # Independently pin the live customer form and history reader to the same
    # release-manifest mapping used by the CLI acceptance ramp.
    assert HARNESS.load_customer_routes() == (
        "startStandardScanJobV8", "getCustomerScanResultV8",
    )
    active = json.loads((ROOT / "data/base44-function-routes.json").read_text())
    assert active["generation"] == "v8"
    assert HARNESS.START_CUSTOMER_FUNCTION == active["routes"]["startStandardScanJob"]
    assert HARNESS.READ_CUSTOMER_FUNCTION == active["routes"]["getCustomerScanResult"]
    form = (ROOT / "src/components/scan/ScanWebsiteForm.jsx").read_text()
    reader = (ROOT / "src/lib/scanRuns.js").read_text()
    assert 'const ASYNC_SCAN_JOB_FUNCTION = "startStandardScanJobV8"' in form
    assert 'base44.functions.invoke("getCustomerScanResultV8"' in reader


def test_ramp_routes_fail_closed_on_legacy_staged_or_unreviewed_mapping(tmp_path):
    current = json.loads((ROOT / "data/base44-function-routes.json").read_text())
    invalid = [
        {**current, "generation": "v9"},
        {**current, "routes": {**current["routes"], "getCustomerScanResult": "getCustomerScanResult"}},
        {**current, "routes": {**current["routes"], "startStandardScanJob": "startStandardScanJob"}},
        {**current, "routes": {**current["routes"], "getCustomerScanResult": "getCustomerScanResultV9"}},
        {**current, "routes": {}},
    ]
    for candidate in invalid:
        path = tmp_path / "candidate-routes.json"
        path.write_text(json.dumps(candidate), encoding="utf-8")
        try:
            HARNESS.load_customer_routes(path)
        except RuntimeError as error:
            assert "refusing legacy aliases" in str(error)
        else:
            raise AssertionError("unsafe customer route mapping passed ramp acceptance")



def _complete_item(scan_id: str = "scan_complete"):
    item = HARNESS.Submission(
        email="acceptance@example.com",
        url="https://example.com",
        project_id="project_1",
    )
    item.scan_id = scan_id
    item.http_status = 200
    item.accepted = True
    item.submitted_at = 100.0
    item.terminal_at = 102.5
    item.run = {
        "id": scan_id,
        "status": "complete",
        "error_code": "",
        "fix_list_id": "fixlist_1",
        "evidence_quality_state": "sufficient",
        "evidence_quality_score": 100,
        "beta_revision_fingerprint": "fingerprint_1",
        "scanner_version": "scanner_1",
        "scanner_build_revision": "build_1",
        "review_version": "review_1",
    }
    item.customer_result = {
        "access": "full",
        "scan_id": scan_id,
        "authority_verified": True,
        "result_integrity_verified": False,
        "release_contract_current": True,
        "fixList": {"id": "fixlist_1"},
        "fixItems": [],
    }
    return item



def test_preview_integrity_does_not_satisfy_full_customer_readback():
    # A real V8 reader can return authority_verified=True for a separately
    # signed unpaid preview without checking the full persisted HMAC.
    item = _complete_item("scan_preview_only")
    item.run.update({
        "coverage_authority_evidence": {"state": "sufficient"},
        "classification_integrity": {"state": "verified"},
        "peak_memory_bytes": 4096,
        "beta_revision_fingerprint": HARNESS.EXPECTED_RELEASE_FINGERPRINT,
    })

    control = HARNESS.report([item], {})
    assert control["passed"] is True
    assert control["authoritative_complete"] == 1
    assert control["results"][0]["acceptance_matrix"]["authority_outcome"]["state"] == "authoritative"

    for access in ("preview", "locked", ""):
        item.customer_result["access"] = access
        observed = HARNESS.report([item], {})
        expected = "preview_only" if access == "preview" else "unverified"
        authority = observed["results"][0]["acceptance_matrix"]["authority_outcome"]
        assert authority["state"] == expected
        assert authority["authority_verified"] is False
        assert authority["preview_integrity_verified"] is (access == "preview")
        assert observed["authoritative_complete"] == 0
        assert observed["passed"] is False
        assert any("lacks full-access customer read-back" in failure for failure in observed["failures"])


def _fully_qualifying_ramp_item(scan_id="scan_accepted"):
    item = _complete_item(scan_id)
    item.run.update({
        "coverage_authority_evidence": {"state": "sufficient"},
        "classification_integrity": {"state": "verified"},
        "peak_memory_bytes": 4096,
        "beta_revision_fingerprint": HARNESS.EXPECTED_RELEASE_FINGERPRINT,
    })
    return item


def _rejected_ramp_item(failure_code):
    item = HARNESS.Submission(
        email="acceptance@example.com",
        url="https://example.com",
        project_id="project_1",
    )
    item.http_status = 503
    item.accepted = False
    item.failure_code = failure_code
    return item


def test_no_accepted_submissions_cannot_pass_release_acceptance():
    rejected = _rejected_ramp_item("scan_admission_unavailable")
    observed = HARNESS.report([rejected], {})
    assert observed["submitted"] == 1
    assert observed["accepted"] == 0
    assert observed["terminal"] == 0
    assert observed["passed"] is False
    assert any("no scan was accepted" in failure for failure in observed["failures"])
    assert any("scan_admission_unavailable" in failure for failure in observed["failures"])
    assert HARNESS.report([], {})["passed"] is False


def test_partially_rejected_ramp_does_not_pass_even_with_one_full_verified_result():
    winner = _fully_qualifying_ramp_item()
    assert HARNESS.report([winner], {})["passed"] is True
    rejected = _rejected_ramp_item("admission_capacity_limited")
    observed = HARNESS.report([winner, rejected], {})
    assert observed["authoritative_complete"] == 1
    assert observed["passed"] is False
    assert any("admission_capacity_limited" in failure for failure in observed["failures"])


def test_expected_busy_double_submit_exception_is_narrow():
    winner = _fully_qualifying_ramp_item()
    busy = _rejected_ramp_item("scan_admission_busy")
    control = HARNESS.report([winner, busy], {}, allow_busy_rejection=True)
    assert control["passed"] is True
    assert control["authoritative_complete"] == 1

    # The same busy rejection is unexpected during an ordinary canary.
    assert HARNESS.report([winner, busy], {})["passed"] is False

    # The double-submit flag must not excuse a different rejection or
    # turn two denied admissions into a successful release receipt.
    busy.failure_code = "scan_admission_unavailable"
    unexpected = HARNESS.report([winner, busy], {}, allow_busy_rejection=True)
    assert unexpected["passed"] is False
    assert any("scan_admission_unavailable" in x for x in unexpected["failures"])
    busy.failure_code = "scan_admission_busy"
    assert HARNESS.report([busy], {}, allow_busy_rejection=True)["passed"] is False


def test_fresh_reopen_downgrade_fails_even_if_terminal_poll_was_full(monkeypatch):
    item = _fully_qualifying_ramp_item("scan_reopen_preview")
    assert HARNESS.report([item], {})["passed"] is True  # cached poll baseline

    async def fresh_preview(_client, _token, function, payload):
        assert function == HARNESS.READ_CUSTOMER_FUNCTION
        assert payload == {"action": "get", "scan_id": item.scan_id}
        return 200, {
            **item.customer_result,
            "scan_id": item.scan_id,
            "run": dict(item.run),
            "access": "preview",
            "authority_verified": True,
        }

    monkeypatch.setattr(HARNESS, "invoke", fresh_preview)
    errors = asyncio.run(HARNESS.reopen_customer_results(
        object(), {item.email: "fake-token"}, [item],
    ))
    assert errors == []
    assert item.customer_result["access"] == "preview"
    observed = HARNESS.report([item], {})
    assert observed["passed"] is False
    assert any("lacks full-access customer read-back" in x for x in observed["failures"])


def test_failed_fresh_reopen_never_reuses_green_terminal_poll(monkeypatch):
    item = _fully_qualifying_ramp_item("scan_reopen_503")
    assert HARNESS.report([item], {})["passed"] is True

    async def unavailable(_client, _token, _function, _payload):
        return 503, {"failure_code": "temporarily_unavailable"}

    monkeypatch.setattr(HARNESS, "invoke", unavailable)
    errors = asyncio.run(HARNESS.reopen_customer_results(
        object(), {item.email: "fake-token"}, [item],
    ))
    assert errors == [f"{item.scan_id}: fresh customer read-back HTTP 503"]
    assert item.customer_result == {}
    assert HARNESS.report([item], {})["passed"] is False


def test_fresh_reopen_rejects_foreign_scan_and_regressed_terminal(monkeypatch):
    for scenario in ("foreign_scan", "regressed_status"):
        item = _fully_qualifying_ramp_item(f"scan_{scenario}")

        async def wrong_read(_client, _token, _function, _payload):
            fresh_run = dict(item.run)
            if scenario == "regressed_status":
                fresh_run["status"] = "crawling"
            return 200, {
                **item.customer_result,
                "scan_id": "different_scan" if scenario == "foreign_scan" else item.scan_id,
                "run": fresh_run,
            }

        monkeypatch.setattr(HARNESS, "invoke", wrong_read)
        errors = asyncio.run(HARNESS.reopen_customer_results(
            object(), {item.email: "fake-token"}, [item],
        ))
        assert len(errors) == 1
        assert ("identity mismatch" if scenario == "foreign_scan" else "terminal status changed") in errors[0]
        assert item.customer_result == {}
        assert HARNESS.report([item], {})["passed"] is False


def test_successful_fresh_reopen_retains_full_and_limited_contracts(monkeypatch):
    for status in ("complete", "limited"):
        item = _fully_qualifying_ramp_item(f"scan_reopened_{status}")
        item.run["status"] = status
        if status == "limited":
            item.run["error_code"] = "scan_access_limited"
            item.customer_result.update({
                "access": "full", "authority_verified": False,
                "result_integrity_verified": True, "fixList": None, "fixItems": [],
            })
        fresh_body = {**item.customer_result, "run": dict(item.run)}

        async def fresh_read(_client, _token, function, payload):
            assert function == HARNESS.READ_CUSTOMER_FUNCTION
            assert payload["scan_id"] == item.scan_id
            return 200, fresh_body

        monkeypatch.setattr(HARNESS, "invoke", fresh_read)
        errors = asyncio.run(HARNESS.reopen_customer_results(
            object(), {item.email: "fake-token"}, [item],
        ))
        assert errors == []
        observed = HARNESS.report([item], {})
        assert observed["passed"] is True
        assert observed["authoritative_complete"] == (1 if status == "complete" else 0)


def test_main_exit_fails_when_independent_customer_reopen_is_unavailable(tmp_path, monkeypatch, capsys):
    # Full integration through main_async: the cached terminal result is green,
    # but the fresh customer GET on a separate client fails closed.
    async def fake_submit(_client, _token, item):
        seeded = _fully_qualifying_ramp_item("scan_reopen_integration")
        item.scan_id = seeded.scan_id
        item.accepted = True
        item.http_status = 200
        item.submitted_at = seeded.submitted_at
        item.terminal_at = seeded.terminal_at
        item.run = seeded.run
        item.customer_result = seeded.customer_result
        assert HARNESS.report([item], {})["passed"] is True

    async def fake_wait(_client, _tokens, _items, _timeout, *, checkpoint_path=""):
        return None

    async def unavailable_reopen(_client, _token, function, payload):
        assert function == HARNESS.READ_CUSTOMER_FUNCTION
        assert payload == {"action": "get", "scan_id": "scan_reopen_integration"}
        return 503, {"failure_code": "temporarily_unavailable"}

    monkeypatch.setattr(HARNESS.httpx, "AsyncClient", _DummyAsyncClient)
    monkeypatch.setattr(HARNESS, "submit", fake_submit)
    monkeypatch.setattr(HARNESS, "wait_terminal", fake_wait)
    monkeypatch.setattr(HARNESS, "invoke", unavailable_reopen)
    monkeypatch.setattr(HARNESS, "log_quality", lambda *_args: {"available": False})

    status = asyncio.run(HARNESS.main_async(_main_args(tmp_path, checkpoint="")))
    receipt = json.loads(capsys.readouterr().out)
    assert status == 1
    assert receipt["passed"] is False
    assert any("fresh customer read-back HTTP 503" in failure for failure in receipt["failures"])
    assert receipt["authoritative_complete"] == 0


def test_failed_and_cancelled_terminals_never_pass_customer_acceptance():
    # Negative controls keep all ten dimensions measured and the exact
    # release matched, so failure must derive from terminal outcome itself.
    for status in ("failed", "cancelled"):
        item = _fully_qualifying_ramp_item(f"scan_{status}")
        item.run["status"] = status
        item.run["error_code"] = "worker_failed" if status == "failed" else "owner_cancelled"
        item.customer_result.update({
            "access": "locked",
            "authority_verified": False,
            "fixList": None,
            "fixItems": [],
        })
        observed = HARNESS.report([item], {})
        assert observed["terminal"] == 1
        assert observed["authoritative_complete"] == 0
        assert observed["results"][0]["matrix_gaps"] == []
        assert observed["results"][0]["matrix_failures"] == []
        assert observed["passed"] is False
        assert any(
            f"unsuccessful terminal status {status}" in failure
            for failure in observed["failures"]
        )


def test_integrity_verified_limited_terminal_remains_success_eligible():
    # A correctly limited but integrity-verified customer result is a
    # legitimate Standard 150 outcome; do not regress that existing contract.
    item = _fully_qualifying_ramp_item("scan_limited")
    item.run["status"] = "limited"
    item.run["error_code"] = "scan_access_limited"
    item.customer_result.update({
        "access": "limited",
        "authority_verified": False,
        "result_integrity_verified": True,
        "fixList": None,
        "fixItems": [],
    })
    observed = HARNESS.report([item], {})
    assert observed["terminal"] == 1
    assert observed["limited"] == 1
    assert observed["results"][0]["matrix_gaps"] == []
    assert observed["passed"] is True


def test_matrix_has_ten_independent_dimensions_and_only_real_gaps():
    item = _complete_item()
    matrix = build_acceptance_matrix(HARNESS._matrix_observation(item))

    assert set(matrix) == set(REQUIRED_MATRIX_DIMENSIONS)
    assert matrix["infrastructure_outcome"]["terminal_status"] == "complete"
    assert matrix["authority_outcome"]["state"] == "authoritative"
    assert matrix["evidence_quality_verdict"]["state"] == "sufficient"
    assert matrix["ui_result_route_verdict"]["state"] == "exact"
    assert matrix["duration"]["milliseconds"] == 2500
    assert matrix["exact_release_markers"]["beta_revision_fingerprint"] == "fingerprint_1"

    assert set(_matrix_contract_gaps(matrix)) == {
        "coverage_sufficiency",
        "classification_verdict",
        "memory_resource_result",
    }


def test_healthy_complete_scan_measures_absence_of_limited_access():
    matrix = build_acceptance_matrix(HARNESS._matrix_observation(_complete_item()))
    dimension = matrix["limited_access_failure_class"]

    assert dimension == {
        "available": True,
        "state": "none",
        "limited": False,
        "failure_class": "",
    }
    assert "limited_access_failure_class" not in _matrix_contract_gaps(matrix)


def test_unprojected_limited_access_dimension_is_still_a_gap():
    matrix = build_acceptance_matrix({})

    assert matrix["limited_access_failure_class"]["available"] is False
    assert "limited_access_failure_class" in _matrix_contract_gaps(matrix)


def test_failed_access_limited_scan_records_its_real_class():
    matrix = build_acceptance_matrix({
        "scan_id": "scan_failed",
        "http_status": 200,
        "accepted": True,
        "run": {
            "id": "scan_failed",
            "status": "failed",
            "error_code": "scan_access_limited",
        },
        "customer_result": {
            "scan_id": "scan_failed",
            "authority_verified": False,
            "result_integrity_verified": False,
        },
    })
    dimension = matrix["limited_access_failure_class"]

    assert dimension["available"] is True
    assert dimension["state"] == "limited"
    assert dimension["limited"] is True
    assert dimension["failure_class"] == "scan_access_limited"


def test_integrity_only_limited_scan_records_its_class():
    item = _complete_item("scan_limited")
    item.run.update({
        "status": "limited",
        "error_code": "access_limited_429",
    })
    item.customer_result.update({
        "authority_verified": False,
        "result_integrity_verified": True,
    })
    matrix = build_acceptance_matrix(HARNESS._matrix_observation(item))

    assert matrix["authority_outcome"]["state"] == "integrity_only"
    assert matrix["limited_access_failure_class"]["failure_class"] == "access_limited_429"


def test_archetype_label_is_not_invented_as_classification_verdict():
    item = _complete_item()
    item.run["business_archetype"] = "ecommerce"
    matrix = build_acceptance_matrix(HARNESS._matrix_observation(item))

    assert matrix["classification_verdict"]["available"] is False
    assert matrix["classification_verdict"]["state"] == "unavailable"


def test_exact_result_route_mismatch_is_a_matrix_failure():
    item = _complete_item()
    item.customer_result["scan_id"] = "different_scan"
    matrix = build_acceptance_matrix(HARNESS._matrix_observation(item))

    assert matrix["ui_result_route_verdict"]["state"] == "mismatch"
    assert "ui_result_route_mismatch" in _matrix_contract_gaps(matrix)


def test_admission_failure_code_is_consistent_in_matrix_and_summary():
    item = HARNESS.Submission(
        email="acceptance@example.com",
        url="https://example.com",
        project_id="project_1",
    )
    item.http_status = 429
    item.accepted = False
    item.failure_code = "admission_capacity_limited"

    summary = HARNESS._result_summary(item)

    assert summary["error_code"] == "admission_capacity_limited"
    assert (
        summary["acceptance_matrix"]["infrastructure_outcome"]["failure_code"]
        == "admission_capacity_limited"
    )


def test_exact_release_wrapper_preserves_base_release_markers(monkeypatch):
    item = _complete_item("scan_exact_markers")
    item.run.update({
        "beta_revision_fingerprint": "0123456789abcdef",
        "review_evidence_calibration_version": "calibration_1",
        "archetype_classifier_version": "classifier_1",
    })
    item.customer_result["release_contract_current"] = True
    monkeypatch.setattr(
        HARNESS,
        "EXPECTED_RELEASE_FINGERPRINT",
        "0123456789abcdef",
    )

    exact = HARNESS.build_acceptance_matrix(
        HARNESS._matrix_observation(item)
    )["exact_release_markers"]

    assert exact["state"] == "match"
    assert exact["scanner_version"] == "scanner_1"
    assert exact["scanner_build_revision"] == "build_1"
    assert exact["review_version"] == "review_1"
    assert exact["review_evidence_calibration_version"] == "calibration_1"
    assert exact["archetype_classifier_version"] == "classifier_1"


def test_terminal_poll_durably_checkpoints_the_completed_site(
    tmp_path,
    monkeypatch,
):
    item = _complete_item("scan_1")
    item.terminal_at = 0.0
    item.run = {}
    item.customer_result = {}
    checkpoint = tmp_path / "acceptance.json"

    async def fake_invoke(_client, _token, function, payload):
        assert function == HARNESS.READ_CUSTOMER_FUNCTION
        assert payload == {"action": "get", "scan_id": "scan_1"}
        return 200, {
            "scan_id": "scan_1",
            "run": {
                "id": "scan_1",
                "status": "complete",
                "fix_list_id": "fixlist_1",
                "evidence_quality_state": "sufficient",
                "beta_revision_fingerprint": "fingerprint_1",
            },
            "authority_verified": True,
            "release_contract_current": True,
            "fixList": {"id": "fixlist_1"},
            "fixItems": [],
        }

    monkeypatch.setattr(HARNESS, "invoke", fake_invoke)
    asyncio.run(HARNESS.wait_terminal(
        object(),
        {item.email: "token"},
        [item],
        1,
        checkpoint_path=str(checkpoint),
    ))

    persisted = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert persisted["completed_sites"] == 1
    assert persisted["sites"][0]["scan_id"] == "scan_1"
    assert set(persisted["sites"][0]["acceptance_matrix"]) == set(
        REQUIRED_MATRIX_DIMENSIONS
    )




def test_transition_checkpoint_failure_does_not_abort_terminal_reporting(
    tmp_path,
    monkeypatch,
    capsys,
):
    item = _complete_item("scan_checkpoint_failure")
    item.terminal_at = 0.0
    item.run = {}
    item.customer_result = {}

    async def fake_invoke(_client, _token, function, payload):
        assert function == HARNESS.READ_CUSTOMER_FUNCTION
        return 200, {
            "scan_id": payload["scan_id"],
            "run": {
                "id": payload["scan_id"],
                "status": "complete",
                "fix_list_id": "fixlist_checkpoint_failure",
                "evidence_quality_state": "sufficient",
                "beta_revision_fingerprint": "fingerprint_1",
            },
            "authority_verified": True,
            "release_contract_current": True,
            "fixList": {"id": "fixlist_checkpoint_failure"},
            "fixItems": [],
        }

    def failed_checkpoint(*_args):
        raise OSError("transition fsync failed")

    monkeypatch.setattr(HARNESS, "invoke", fake_invoke)
    monkeypatch.setattr(HARNESS, "write_checkpoint", failed_checkpoint)

    asyncio.run(HARNESS.wait_terminal(
        object(),
        {item.email: "token"},
        [item],
        1,
        checkpoint_path=str(tmp_path / "checkpoint.json"),
    ))

    assert item.terminal_at > 0
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert {
        "event": "checkpoint_write_error",
        "error_type": "OSError",
    } in events


def test_poll_failure_does_not_cancel_sibling_or_lose_checkpoint(
    tmp_path,
    monkeypatch,
):
    first = _complete_item("scan_retry")
    second = _complete_item("scan_complete")
    for item in (first, second):
        item.terminal_at = 0.0
        item.run = {}
        item.customer_result = {}

    attempts = {"scan_retry": 0}

    async def fake_invoke(_client, _token, function, payload):
        assert function == HARNESS.READ_CUSTOMER_FUNCTION
        scan_id = payload["scan_id"]
        if scan_id == "scan_retry":
            attempts[scan_id] += 1
            if attempts[scan_id] == 1:
                raise HARNESS.httpx.ReadTimeout("transient")
        return 200, {
            "scan_id": scan_id,
            "run": {
                "id": scan_id,
                "status": "complete",
                "fix_list_id": f"fixlist_{scan_id}",
                "evidence_quality_state": "sufficient",
                "beta_revision_fingerprint": "fingerprint_1",
            },
            "authority_verified": True,
            "release_contract_current": True,
            "fixList": {"id": f"fixlist_{scan_id}"},
            "fixItems": [],
        }

    async def no_delay(_seconds):
        return None

    checkpoint = tmp_path / "acceptance.json"
    monkeypatch.setattr(HARNESS, "invoke", fake_invoke)
    monkeypatch.setattr(HARNESS.asyncio, "sleep", no_delay)

    asyncio.run(HARNESS.wait_terminal(
        object(),
        {first.email: "token", second.email: "token"},
        [first, second],
        1,
        checkpoint_path=str(checkpoint),
    ))

    persisted = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert attempts["scan_retry"] == 2
    assert persisted["completed_sites"] == 2
    assert {site["scan_id"] for site in persisted["sites"]} == {
        "scan_retry",
        "scan_complete",
    }


def test_checkpoint_is_atomic_fsynced_compact_and_preserves_prior_sites(
    tmp_path,
    monkeypatch,
):
    first = _complete_item("scan_1")
    second = _complete_item("scan_2")
    second.terminal_at = 0.0
    second.run = {"id": "scan_2", "status": "crawling"}
    second.customer_result = {"scan_id": "scan_2", "run": dict(second.run)}
    checkpoint = tmp_path / "acceptance.json"
    fsync_calls = []
    real_fsync = HARNESS.os.fsync

    def observed_fsync(fd):
        fsync_calls.append(fd)
        return real_fsync(fd)

    monkeypatch.setattr(HARNESS.os, "fsync", observed_fsync)
    HARNESS.write_checkpoint(str(checkpoint), [first, second])

    first_write = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert [site["scan_id"] for site in first_write["sites"]] == ["scan_1"]
    assert "acceptance@example.com" not in checkpoint.read_text(encoding="utf-8")
    assert "Bearer " not in checkpoint.read_text(encoding="utf-8")
    assert "fixItems" not in checkpoint.read_text(encoding="utf-8")
    assert len(fsync_calls) == 2
    assert list(tmp_path.glob("*.tmp")) == []

    second.terminal_at = 105.0
    second.run.update({
        "status": "complete",
        "evidence_quality_state": "sufficient",
        "beta_revision_fingerprint": "fingerprint_1",
    })
    second.customer_result.update({
        "authority_verified": True,
        "release_contract_current": True,
        "fixList": {"id": "fixlist_2"},
        "fixItems": [],
    })
    HARNESS.write_checkpoint(str(checkpoint), [first, second])

    second_write = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert [site["scan_id"] for site in second_write["sites"]] == [
        "scan_1",
        "scan_2",
    ]


def test_final_aggregate_cannot_pass_with_unmeasured_dimensions():
    result = HARNESS.report(
        [_complete_item()],
        {"available": False, "reason": "test"},
    )

    assert result["passed"] is False
    assert any(
        "coverage_sufficiency" in failure
        and "classification_verdict" in failure
        and "memory_resource_result" in failure
        for failure in result["failures"]
    )


def test_projected_acceptance_evidence_closes_the_three_observation_gaps():
    item = _complete_item("scan_observed")
    item.run.update({
        "coverage_authority_evidence": {
            "coverage_authority_evidence_version": "coverage_authority_evidence_v2_authoritative",
            "assessment": "sufficient",
        },
        "classification_integrity": {
            "state": "classified",
            "classifier_version": "classifier_1",
        },
        "classification_verdict": "classified",
        "worker_peak_memory_bytes": 268_435_456,
    })

    matrix = HARNESS.build_acceptance_matrix(HARNESS._matrix_observation(item))

    assert matrix["coverage_sufficiency"]["state"] == "sufficient"
    assert matrix["classification_verdict"]["state"] == "classified"
    assert matrix["memory_resource_result"] == {
        "available": True,
        "state": "measured",
        "peak_memory_bytes": 268_435_456,
        "failure_code": "",
        "reason": "",
    }
    assert not {
        "coverage_sufficiency",
        "classification_verdict",
        "memory_resource_result",
    } & set(_matrix_contract_gaps(matrix))


class _DummyAsyncClient:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *_args):
        return None


def _main_args(tmp_path, *, checkpoint):
    tokens = tmp_path / "tokens.json"
    targets = tmp_path / "targets.json"
    tokens.write_text(json.dumps({"acceptance@example.com": "test-token"}), encoding="utf-8")
    targets.write_text(json.dumps([{
        "email": "acceptance@example.com",
        "url": "https://example.com",
        "project_id": "project_1",
    }]), encoding="utf-8")
    return SimpleNamespace(
        tokens=str(tokens),
        targets=str(targets),
        count=1,
        double_submit=False,
        timeout=1,
        checkpoint=checkpoint,
        gcp_project="",
    )


def _stub_main_dependencies(monkeypatch):
    async def no_submit(_client, _token, _item):
        return None

    async def no_wait(_client, _tokens, _items, _timeout, *, checkpoint_path=""):
        return None

    monkeypatch.setattr(HARNESS.httpx, "AsyncClient", _DummyAsyncClient)
    monkeypatch.setattr(HARNESS, "submit", no_submit)
    monkeypatch.setattr(HARNESS, "wait_terminal", no_wait)
    monkeypatch.setattr(HARNESS, "log_quality", lambda *_args: {"available": False})
    monkeypatch.setattr(HARNESS, "report", lambda *_args: {
        "failures": [],
        "passed": True,
        "results": [],
    })


def test_final_report_prints_when_checkpoint_is_disabled(tmp_path, monkeypatch, capsys):
    _stub_main_dependencies(monkeypatch)

    def unexpected_checkpoint(*_args):
        raise AssertionError("disabled checkpoint must not be written")

    monkeypatch.setattr(HARNESS, "write_checkpoint", unexpected_checkpoint)

    status = asyncio.run(HARNESS.main_async(_main_args(tmp_path, checkpoint="")))
    printed = json.loads(capsys.readouterr().out)

    assert status == 0
    assert printed["passed"] is True


def test_final_report_survives_checkpoint_failure(tmp_path, monkeypatch, capsys):
    _stub_main_dependencies(monkeypatch)

    def failed_checkpoint(*_args):
        raise OSError("filesystem refused directory fsync")

    monkeypatch.setattr(HARNESS, "write_checkpoint", failed_checkpoint)

    status = asyncio.run(HARNESS.main_async(_main_args(
        tmp_path,
        checkpoint=str(tmp_path / "checkpoint.json"),
    )))
    printed = json.loads(capsys.readouterr().out)

    assert status == 1
    assert printed["passed"] is False
    assert printed["failures"] == ["checkpoint write failed: OSError"]


def test_real_harness_requires_the_exact_release_under_acceptance(monkeypatch):
    item = _complete_item("scan_exact_release")
    item.run["beta_revision_fingerprint"] = "0123456789abcdef"
    item.customer_result["release_contract_current"] = True
    monkeypatch.setattr(HARNESS, "EXPECTED_RELEASE_FINGERPRINT", "0123456789abcdef")
    summary = HARNESS._result_summary(item)
    exact = summary["acceptance_matrix"]["exact_release_markers"]
    assert exact["available"] is True
    assert exact["matches"] is True
    assert exact["state"] == "match"
    assert "exact_release_markers" not in summary["matrix_gaps"]
    assert "exact_release_markers" not in summary["matrix_failures"]


def test_real_harness_rejects_historical_valid_but_not_current_release(monkeypatch):
    item = _complete_item("scan_historical")
    item.run["beta_revision_fingerprint"] = "fedcba9876543210"
    item.customer_result["release_contract_current"] = True
    monkeypatch.setattr(HARNESS, "EXPECTED_RELEASE_FINGERPRINT", "0123456789abcdef")
    summary = HARNESS._result_summary(item)
    exact = summary["acceptance_matrix"]["exact_release_markers"]
    assert exact["available"] is True
    assert exact["matches"] is False
    assert exact["state"] == "mismatch"
    assert "exact_release_markers" in summary["matrix_failures"]


def test_real_harness_missing_release_fingerprint_remains_a_gap(monkeypatch):
    item = _complete_item("scan_missing_marker")
    item.run.pop("beta_revision_fingerprint", None)
    item.customer_result["release_contract_current"] = True
    monkeypatch.setattr(HARNESS, "EXPECTED_RELEASE_FINGERPRINT", "0123456789abcdef")
    summary = HARNESS._result_summary(item)
    exact = summary["acceptance_matrix"]["exact_release_markers"]
    assert exact["available"] is False
    assert exact["state"] == "unavailable"
    assert "exact_release_markers" in summary["matrix_gaps"]


def test_final_aggregate_fails_on_stale_exact_release_even_when_marker_is_present(
    monkeypatch,
):
    item = _complete_item("scan_wrong_release")
    item.run["beta_revision_fingerprint"] = "fedcba9876543210"
    item.customer_result["release_contract_current"] = True
    monkeypatch.setattr(HARNESS, "EXPECTED_RELEASE_FINGERPRINT", "0123456789abcdef")
    result = HARNESS.report(
        [item],
        {"available": False, "reason": "test"},
    )
    assert result["passed"] is False
    assert any(
        "exact_release_markers" in failure
        and "failed required evidence" in failure
        for failure in result["failures"]
    )
