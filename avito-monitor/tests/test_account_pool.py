"""Tests for AccountPool client."""
import pytest
import respx
from httpx import AsyncClient, Response

from app.services.account_pool import (
    AccountPool, NoAvailableAccountError, AccountNotAvailableError,
)


XAPI_URL = "http://xapi-test:8080"


@pytest.fixture
def pool():
    client = AsyncClient(base_url=XAPI_URL, headers={"X-Api-Key": "test"})
    return AccountPool(xapi_client=client)


@pytest.mark.asyncio
async def test_claim_for_poll_returns_session(pool):
    with respx.mock(base_url=XAPI_URL) as m:
        m.post("/api/v1/accounts/poll-claim").mock(
            return_value=Response(200, json={
                "account_id": "acc-1", "session_token": "T1",
                "device_id": "D1", "fingerprint": "F1",
            }),
        )
        async with pool.claim_for_poll() as acc:
            assert acc["account_id"] == "acc-1"
            assert acc["session_token"] == "T1"


@pytest.mark.asyncio
async def test_claim_for_poll_409_raises_no_available(pool):
    with respx.mock(base_url=XAPI_URL) as m:
        m.post("/api/v1/accounts/poll-claim").mock(
            return_value=Response(409, json={
                "detail": {"error": "pool_drained", "accounts": []}
            }),
        )
        with pytest.raises(NoAvailableAccountError):
            async with pool.claim_for_poll():
                pass


@pytest.mark.asyncio
async def test_report_truncates_body_to_1024(pool):
    captured = {}
    def capture(request):
        captured["json"] = request.read().decode()
        return Response(204)
    with respx.mock(base_url=XAPI_URL) as m:
        m.post("/api/v1/accounts/acc-1/report").mock(side_effect=capture)
        await pool.report("acc-1", 403, body="x" * 5000)
        import json
        body = json.loads(captured["json"])
        assert len(body["body_excerpt"]) == 1024


@pytest.mark.asyncio
async def test_report_none_body_sends_null(pool):
    captured = {}
    def capture(request):
        captured["json"] = request.read().decode()
        return Response(204)
    with respx.mock(base_url=XAPI_URL) as m:
        m.post("/api/v1/accounts/acc-1/report").mock(side_effect=capture)
        await pool.report("acc-1", 200, body=None)
        import json
        body = json.loads(captured["json"])
        assert body["body_excerpt"] is None


@pytest.mark.asyncio
async def test_claim_for_sync_409_raises_account_not_available(pool):
    with respx.mock(base_url=XAPI_URL) as m:
        m.get("/api/v1/accounts/acc-1/session-for-sync").mock(
            return_value=Response(409, json={"detail": {"state": "cooldown"}}),
        )
        with pytest.raises(AccountNotAvailableError) as ei:
            await pool.claim_for_sync("acc-1")
        assert ei.value.state == "cooldown"


@pytest.mark.asyncio
async def test_list_active_accounts_filters(pool):
    with respx.mock(base_url=XAPI_URL) as m:
        m.get("/api/v1/accounts").mock(return_value=Response(200, json=[
            {"id": "a1", "state": "active", "nickname": "Clone"},
            {"id": "a2", "state": "cooldown", "nickname": "Main"},
            {"id": "a3", "state": "active", "nickname": "Other"},
        ]))
        result = await pool.list_active_accounts()
        assert {a["nickname"] for a in result} == {"Clone", "Other"}
