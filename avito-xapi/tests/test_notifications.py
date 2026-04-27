"""Tests for V2.1 notifications router (POST + stats)."""
from unittest.mock import MagicMock, patch

from tests.conftest import make_authed_sb, run_request


def test_ingest_notification_minimal():
    """POST /notifications with bare-minimum payload → 201, db_id returned."""
    mock_sb = make_authed_sb(
        [{"id": 42, "tenant_id": "c0000000-0000-0000-0000-000000000001"}],  # insert
    )
    fake_wm = MagicMock()
    fake_wm.broadcast_to_tenant = MagicMock(return_value=False)

    with patch("src.routers.notifications.ws_manager", fake_wm):
        resp = run_request(
            mock_sb,
            method="POST",
            path="/api/v1/notifications",
            json_body={"source": "android_notification"},
            extra_patches={"src.routers.notifications.get_supabase": mock_sb},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "ok"
    assert data["notification_id"] == 42
    assert data["broadcast"] is False  # no SSE subscriber in test
    fake_wm.broadcast_to_tenant.assert_called_once()


def test_ingest_notification_full_payload():
    """POST /notifications with full Avito-shaped payload → 201, broadcasts."""
    mock_sb = make_authed_sb([{"id": 100}])
    fake_wm = MagicMock()
    fake_wm.broadcast_to_tenant = MagicMock(return_value=True)

    payload = {
        "source": "android_notification",
        "package_name": "com.avito.android",
        "notification_id": 12345,
        "tag": "u2i-abc123",
        "title": "Иван",
        "text": "Здравствуйте, актуально?",
        "big_text": "Здравствуйте, актуально? Готов забрать сегодня.",
        "sub_text": "Сообщения",
        "extras": {"android.template": "MessagingStyle"},
    }

    with patch("src.routers.notifications.ws_manager", fake_wm):
        resp = run_request(
            mock_sb,
            method="POST",
            path="/api/v1/notifications",
            json_body=payload,
            extra_patches={"src.routers.notifications.get_supabase": mock_sb},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["notification_id"] == 100
    assert data["broadcast"] is True


def test_ingest_notification_broadcasts_correct_payload():
    """The broadcast call carries the expected event-name and payload shape."""
    mock_sb = make_authed_sb([{"id": 7}])
    fake_wm = MagicMock()
    fake_wm.broadcast_to_tenant = MagicMock(return_value=True)

    with patch("src.routers.notifications.ws_manager", fake_wm):
        resp = run_request(
            mock_sb,
            method="POST",
            path="/api/v1/notifications",
            json_body={
                "source": "android_notification",
                "package_name": "com.avito.android",
                "tag": "u2i-XYZ",
                "title": "Иван",
                "text": "Готов?",
            },
            extra_patches={"src.routers.notifications.get_supabase": mock_sb},
        )

    assert resp.status_code == 201

    args, _ = fake_wm.broadcast_to_tenant.call_args
    tenant_id_arg, event_name_arg, payload_arg = args
    assert tenant_id_arg == "c0000000-0000-0000-0000-000000000001"
    assert event_name_arg == "notification_intercepted"
    assert payload_arg["db_id"] == 7
    assert payload_arg["tag"] == "u2i-XYZ"
    assert payload_arg["title"] == "Иван"
    assert payload_arg["body"] == "Готов?"
    assert payload_arg["package_name"] == "com.avito.android"


def test_ingest_notification_no_auth():
    """Missing X-Api-Key → 401."""
    from fastapi.testclient import TestClient
    from src.main import app

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/api/v1/notifications", json={"source": "android_notification"})
    assert resp.status_code == 401


def test_ingest_notification_persisted_no_id():
    """Insert returns empty (unexpected) → 201 with status='persisted_no_id'."""
    mock_sb = make_authed_sb([])  # empty insert response

    resp = run_request(
        mock_sb,
        method="POST",
        path="/api/v1/notifications",
        json_body={"source": "android_notification"},
        extra_patches={"src.routers.notifications.get_supabase": mock_sb},
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "persisted_no_id"
    assert data["notification_id"] == 0
    assert data["broadcast"] is False


def test_stats_empty():
    """GET /notifications/stats with no rows → all zeros."""
    mock_sb = make_authed_sb([])
    extra_patches = {"src.routers.notifications.get_supabase": mock_sb}

    resp = run_request(
        mock_sb,
        method="GET",
        path="/api/v1/notifications/stats",
        extra_patches=extra_patches,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["last_24h"] == 0
    assert data["last_received_at"] is None
    assert data["by_source"] == {}


def test_stats_with_rows():
    """GET /notifications/stats with mixed rows → aggregates by source/package."""
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    fresh = (now - timedelta(hours=1)).isoformat()
    older = (now - timedelta(days=2)).isoformat()

    rows = [
        {"id": 1, "source": "android_notification", "package_name": "com.avito.android", "received_at": fresh},
        {"id": 2, "source": "android_notification", "package_name": "com.avito.android", "received_at": fresh},
        {"id": 3, "source": "android_notification", "package_name": "com.avito.android", "received_at": older},
        {"id": 4, "source": "test", "package_name": "com.test", "received_at": fresh},
    ]
    mock_sb = make_authed_sb(rows)
    extra_patches = {"src.routers.notifications.get_supabase": mock_sb}

    resp = run_request(
        mock_sb,
        method="GET",
        path="/api/v1/notifications/stats",
        extra_patches=extra_patches,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 4
    assert data["last_24h"] == 3  # 3 fresh, 1 older than 24h
    assert data["by_source"]["android_notification"] == 3
    assert data["by_source"]["test"] == 1
    assert data["by_package"]["com.avito.android"] == 3
    assert data["by_package"]["com.test"] == 1
    assert data["last_received_at"] is not None


def test_ws_manager_broadcast_to_tenant_no_subscriber():
    """ws_manager.broadcast_to_tenant returns False when no subscriber exists."""
    from src.workers.ws_manager import WsManager

    wm = WsManager()
    # No connections created → broadcast must be a no-op returning False.
    result = wm.broadcast_to_tenant(
        "c0000000-0000-0000-0000-000000000001",
        "notification_intercepted",
        {"hello": "world"},
    )
    assert result is False


def test_ws_manager_broadcast_to_tenant_with_subscriber():
    """ws_manager.broadcast_to_tenant pushes event into subscriber queue."""
    import asyncio
    from src.workers.ws_manager import WsManager, TenantConnection

    async def _run():
        wm = WsManager()
        wm.init(asyncio.get_running_loop())
        # Inject a fake connection without booting a real WS client.
        fake_client = MagicMock()
        conn = TenantConnection("tid-1", fake_client, asyncio.get_running_loop())
        wm._connections["tid-1"] = conn
        q: asyncio.Queue = asyncio.Queue(maxsize=10)
        conn.subscribers.append(q)

        ok = wm.broadcast_to_tenant("tid-1", "notification_intercepted", {"foo": "bar"})
        assert ok is True

        evt = await asyncio.wait_for(q.get(), timeout=1.0)
        assert evt["event"] == "notification_intercepted"
        assert evt["tenant_id"] == "tid-1"
        assert evt["payload"]["foo"] == "bar"
        assert "timestamp" in evt

    asyncio.run(_run())
