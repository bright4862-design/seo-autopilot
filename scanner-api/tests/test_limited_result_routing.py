"""Patch C part 2 - a limited scan reaches the limited path, not the failure path.

Part 1 makes a thin crawl provisional. persistDurableScanAuthority refuses
anything that is not release-eligible, so without this routing Tanners and
Decathlon would stop being wrongly authoritative and start being outright
failures -- losing evidence that was real. That is a worse answer than the
overclaim it replaced, which is exactly what the blueprint warns about.
"""
import pytest

from app import scan_job
from app.scan_job import (
    LIMITED_COMPLETION_VERSION,
    LIMITED_COVERAGE_STATES,
    build_limited_envelope,
    coverage_state_of,
    limited_result_payload,
)


def review(state="limited_coverage", *, reasons=None, fixes=1, eligible=False):
    return {
        "scan_status": "inconclusive_insufficient_evidence",
        "health_score": 48,
        "health_grade": "Insufficient evidence",
        "limitation": "FixList reviewed 38 of 3,689 discovered pages.",
        "release_gate_eligible": eligible,
        "score_is_provisional": not eligible,
        "recommendations": [{"fix_id": f"fix_{i}", "issue_title": f"F{i}"} for i in range(fixes)],
        "site_fingerprint": {
            "coverage_assessment": {
                "state": state,
                "reasons": reasons or ["retained_pages_below_minimum"],
                "coverage_authority_version": "coverage_authority_v1_shared_decision",
            },
        },
    }


def test_the_limited_states_are_the_non_sufficient_ones():
    assert LIMITED_COVERAGE_STATES == {"limited_coverage", "inventory_unproven", "access_limited"}


def test_the_coverage_state_is_read_from_the_shared_assessment():
    assert coverage_state_of(review("inventory_unproven")) == "inventory_unproven"
    assert coverage_state_of({}) == ""


def test_the_limited_payload_binds_the_limitation_and_its_reasons():
    """The limitation is the point of the record, so the proof must cover it."""
    payload = limited_result_payload(review(reasons=["retained_pages_below_minimum", "coverage_ratio_below_minimum"]))

    assert payload["coverage_state"] == "limited_coverage"
    assert payload["coverage_reasons"] == ["retained_pages_below_minimum", "coverage_ratio_below_minimum"]
    assert payload["coverage_authority_version"] == "coverage_authority_v1_shared_decision"
    assert payload["release_gate_eligible"] is False
    assert payload["score_is_provisional"] is True
    assert payload["limitation"]


def test_the_limited_envelope_is_its_own_version_not_the_authority_one():
    envelope = build_limited_envelope(
        {"id": "scan_1", "project_id": "p", "owner_user_id": "o", "attempt_count": 1},
        {"normalized_domain": "www.example.com"},
        review(),
        "signing-key-never-deployed",
    )

    assert envelope["version"] == LIMITED_COMPLETION_VERSION
    assert envelope["version"] != "durable_standard150_completion_v1"
    assert envelope["proof"]
    assert envelope["identity"]["scan_id"] == "scan_1"
    assert envelope["identity"]["normalized_domain"] == "example.com"


def test_the_envelope_never_carries_an_authoritative_review():
    envelope = build_limited_envelope(
        {"id": "scan_1", "project_id": "p", "owner_user_id": "o", "attempt_count": 1},
        {},
        review(),
        "signing-key-never-deployed",
    )
    assert envelope["review"]["release_gate_eligible"] is False


def test_the_worker_routes_limited_coverage_to_the_limited_function():
    """Read from the source: the call must exist and target the right package."""
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "app" / "scan_job.py").read_text(encoding="utf-8")
    assert 'invoke_function(client, "persistLimitedScanResultV2"' in source
    assert "LIMITED_COVERAGE_STATES" in source


def test_a_sufficient_scan_never_takes_the_limited_path():
    assert coverage_state_of(review("sufficient", eligible=True)) not in LIMITED_COVERAGE_STATES


def _scan():
    return {
        "id": "scan_1",
        "project_id": "project_1",
        "owner_user_id": "owner_1",
        "request_id": "request_1",
        "idempotency_key": "request_1",
        "normalized_domain": "example.com",
        "attempt_count": 1,
        "status": "running",
    }


@pytest.mark.asyncio
async def test_noneligible_nonlimited_review_never_reaches_authority_persistence(monkeypatch):
    calls = []

    async def read_fresh(_client, _scan_id):
        return _scan()

    async def invoke(_client, name, _payload, *args, **kwargs):
        calls.append(name)
        raise AssertionError(f"noneligible review reached persistence: {name}")

    monkeypatch.setattr(scan_job, "read_scan_run", read_fresh)
    monkeypatch.setattr(scan_job, "invoke_function", invoke)

    outcome = await scan_job.complete_authority(
        object(),
        _scan(),
        {"pages": []},
        "test-signing-key",
        review={
            "release_gate_eligible": False,
            "coverage_state": "coverage_unverified",
            "recommendations": [],
        },
    )

    assert outcome["ok"] is False
    assert outcome["transient"] is False
    assert outcome["failure_code"] == "review_not_release_eligible"
    assert "verified evidence" in outcome["customer_message"]
    assert calls == []


@pytest.mark.asyncio
async def test_noneligible_useful_limited_review_still_uses_integrity_path(monkeypatch):
    calls = []

    async def read_fresh(_client, _scan_id):
        return _scan()

    async def persist_limited(_client, _scan_row, _result, reviewed, _key, *, phase_started):
        calls.append(("limited", reviewed["release_gate_eligible"], phase_started > 0))
        return {
            "ok": True,
            "transient": False,
            "failure_code": "",
            "limited": True,
            "fix_list_id": "limited_fixlist_1",
        }

    async def forbidden_invoke(_client, name, _payload, *args, **kwargs):
        raise AssertionError(f"limited review reached authority persistence: {name}")

    monkeypatch.setattr(scan_job, "read_scan_run", read_fresh)
    monkeypatch.setattr(scan_job, "persist_limited_result", persist_limited)
    monkeypatch.setattr(scan_job, "invoke_function", forbidden_invoke)

    outcome = await scan_job.complete_authority(
        object(),
        _scan(),
        {"pages": []},
        "test-signing-key",
        review=review("limited_coverage", fixes=1, eligible=False),
    )

    assert outcome["ok"] is True
    assert outcome["limited"] is True
    assert outcome["fix_list_id"] == "limited_fixlist_1"
    assert len(calls) == 1
    assert calls[0][0:2] == ("limited", False)


@pytest.mark.asyncio
async def test_release_eligible_review_keeps_existing_authority_path(monkeypatch):
    calls = []

    async def read_fresh(_client, _scan_id):
        return _scan()

    async def invoke(_client, name, payload, *args, **kwargs):
        calls.append((name, payload))
        assert name == "persistDurableScanAuthorityV2"
        return {
            "status_code": 200,
            "body": {
                "success": True,
                "fixListId": "fixlist_1",
                "fixListVerified": True,
                "scanRun": {
                    "fix_list_id": "fixlist_1",
                    "authority_proof": "a" * 64,
                },
            },
        }

    monkeypatch.setattr(scan_job, "read_scan_run", read_fresh)
    monkeypatch.setattr(scan_job, "invoke_function", invoke)

    eligible = review("sufficient", fixes=1, eligible=True)
    outcome = await scan_job.complete_authority(
        object(),
        _scan(),
        {"pages": [], "normalized_domain": "example.com"},
        "test-signing-key",
        review=eligible,
    )

    assert outcome == {
        "ok": True,
        "transient": False,
        "failure_code": "",
        "fix_list_id": "fixlist_1",
        "authority_proof": "a" * 64,
    }
    assert [name for name, _payload in calls] == ["persistDurableScanAuthorityV2"]
