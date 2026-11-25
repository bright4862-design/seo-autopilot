"""Check real HTTP hop protection without contacting external sites."""

import httpx
import pytest

from app.finalize_probe_guard import FinalizeProbeSuppressed
from app.security import safe_get, safe_get_once
from app.target_contact import TargetContactRetry, TargetContacts, target_contact_scope


NOW = 1_800_000_000
SITE = "https://site.example"
REDIRECT = "https://www.site.example"
SITE_ORIGIN = SITE + ":443"
REDIRECT_ORIGIN = REDIRECT + ":443"


def accepted():
    return {"status_code": 200, "body": {"success": True, "outcome": "acquired", "seconds_remaining": 120}}


def settled():
    return {"status_code": 200, "body": {"success": True, "outcome": "settled"}}


def scope(send):
    return TargetContacts(delivery_id="a" * 32, cutoff=NOW + 120, send=send, clock=lambda: NOW)


@pytest.mark.asyncio
@pytest.mark.parametrize("header", [None, "1200"])
async def test_redirect_hops_have_separate_grants_and_actual_429_receipt(mock_network, header):
    visited = mock_network({
        SITE + "/": {"status": 302, "headers": {"Location": REDIRECT + "/"}},
        REDIRECT + "/": {"status": 429, "headers": {"Retry-After": header} if header else {}},
    })
    events = []

    async def control(action, fields):
        events.append((action, fields, len(visited)))
        return accepted() if action == "acquire_target_contact" else settled()

    async with httpx.AsyncClient(follow_redirects=False) as client, target_contact_scope(scope(control)):
        response = await safe_get(client, SITE + "/")
        assert response.status_code == 429
        with pytest.raises(FinalizeProbeSuppressed):
            await safe_get_once(client, REDIRECT + "/")

    assert [(fields["target_origin"], sent_requests) for action, fields, sent_requests in events
            if action == "acquire_target_contact"] == [(SITE_ORIGIN, 0), (REDIRECT_ORIGIN, 1)]
    assert len(visited) == 2
    receipts = {fields["target_origin"]: fields["receipt"] for action, fields, _ in events if action == "settle_target_contact"}
    assert receipts[SITE_ORIGIN]["observation"] is None
    assert receipts[REDIRECT_ORIGIN]["observation"] == {
        "status_code": 429, "observed_at": NOW, "retry_after_seconds": 1200 if header else 30,
        "expires_source": "retry_after" if header else "default",
    }


@pytest.mark.asyncio
async def test_busy_redirect_does_not_wait_with_an_origin_or_send_a_probe(mock_network):
    visited = mock_network({SITE + "/": {"status": 302, "headers": {"Location": REDIRECT + "/"}}})
    settled_origins = []

    async def control(action, fields):
        if action == "settle_target_contact":
            settled_origins.append(fields["target_origin"])
            return settled()
        if fields["target_origin"] == SITE_ORIGIN:
            return accepted()
        return {"status_code": 409, "body": {"error_code": "target_contact_busy", "retry_after_seconds": 2}}

    async with httpx.AsyncClient(follow_redirects=False) as client:
        with pytest.raises(TargetContactRetry, match="target_contact_busy"):
            async with target_contact_scope(scope(control)):
                await safe_get(client, SITE + "/")
    assert len(visited) == 1
    assert settled_origins == [SITE_ORIGIN]


@pytest.mark.asyncio
async def test_lost_grant_acknowledgement_means_no_egress_but_settlement_can_replay(mock_network):
    visited = mock_network({SITE + "/": {"status": 200}})
    settled_receipts = []

    async def control(action, fields):
        if action == "acquire_target_contact":
            return {"status_code": 503, "body": {}}
        settled_receipts.append(fields)
        return settled() if len(settled_receipts) > 1 else {"status_code": 503, "body": {}}

    async with httpx.AsyncClient(follow_redirects=False) as client:
        with pytest.raises(TargetContactRetry):
            async with target_contact_scope(scope(control)):
                await safe_get_once(client, SITE + "/")
    assert visited == []
    assert len(settled_receipts) == 2
    assert settled_receipts[0] == settled_receipts[1]
    assert settled_receipts[0]["receipt"] == {"drained_at": NOW, "observation": None}


@pytest.mark.asyncio
async def test_recovery_scope_has_no_http_contact(mock_network):
    visited = mock_network({SITE + "/": {"status": 200}})
    async with httpx.AsyncClient(follow_redirects=False) as client, target_contact_scope(scope(None)):
        with pytest.raises(FinalizeProbeSuppressed, match="finalize_optional_probes_unavailable"):
            await safe_get_once(client, SITE + "/")
    assert visited == []
