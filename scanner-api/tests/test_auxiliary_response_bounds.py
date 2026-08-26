import pytest

from app import canonical_validation, robots_policy, trust_discovery
from app.security import DEFAULT_MAX_DECODED_RESPONSE_BYTES, ResponseBodyTooLarge


class _AllowAllRobots:
    def allowed(self, _user_agent, _url):
        return True


@pytest.mark.asyncio
async def test_oversized_robots_degrades_to_unavailable(monkeypatch):
    observed = {}

    async def oversized(_client, _url, *, max_decoded_bytes=None, **_kwargs):
        observed["max_decoded_bytes"] = max_decoded_bytes
        raise ResponseBodyTooLarge("decoded_response_body_exceeded_test_limit")

    monkeypatch.setattr(robots_policy, "safe_get", oversized)

    policy = await robots_policy.load_robots_policy(object(), "https://example.com")

    assert observed["max_decoded_bytes"] == DEFAULT_MAX_DECODED_RESPONSE_BYTES
    assert policy.status == "unavailable"
    assert policy.status_code == 0
    assert policy.rules_known is False


@pytest.mark.asyncio
async def test_oversized_canonical_target_degrades_to_failed_evidence(monkeypatch):
    observed = {}

    async def oversized(_client, _url, *, max_decoded_bytes=None, **_kwargs):
        observed["max_decoded_bytes"] = max_decoded_bytes
        raise ResponseBodyTooLarge("decoded_response_body_exceeded_test_limit")

    monkeypatch.setattr(canonical_validation, "safe_get_once", oversized)

    evidence = await canonical_validation._fetch_target(
        object(),
        "https://example.com/canonical-target",
        _AllowAllRobots(),
        deadline=None,
    )

    assert observed["max_decoded_bytes"] == DEFAULT_MAX_DECODED_RESPONSE_BYTES
    assert evidence["state"] == "target_failed"
    assert evidence["status_code"] == 0
    assert "decoded_response_body_exceeded_test_limit" in evidence["fetch_error"]
    assert evidence["evidence_source"] == "validation"


@pytest.mark.asyncio
async def test_oversized_trust_probe_degrades_to_failed_trust_evidence(monkeypatch):
    observed = {}

    async def oversized(_client, _url, *, max_decoded_bytes=None, **_kwargs):
        observed["max_decoded_bytes"] = max_decoded_bytes
        raise ResponseBodyTooLarge("decoded_response_body_exceeded_test_limit")

    monkeypatch.setattr(trust_discovery, "safe_get", oversized)

    page, evidence = await trust_discovery._fetch_page(
        object(),
        "https://example.com/about",
        "trust_standard_probe",
    )

    assert observed["max_decoded_bytes"] == DEFAULT_MAX_DECODED_RESPONSE_BYTES
    assert page is None
    assert evidence["status_code"] == 0
    assert "decoded_response_body_exceeded_test_limit" in evidence["error"]
