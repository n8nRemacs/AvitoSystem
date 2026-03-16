from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


def test_health_returns_200():
    with patch("src.storage.supabase.get_supabase", return_value=MagicMock()):
        with patch("src.middleware.auth.get_supabase", return_value=MagicMock()):
            from src.main import app
            client = TestClient(app)
            resp = client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert "version" in data


def test_ready_with_supabase():
    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.limit.return_value.execute.return_value = MagicMock(data=[{"id": "x"}])

    with patch("src.storage.supabase.get_supabase", return_value=mock_sb):
        with patch("src.middleware.auth.get_supabase", return_value=mock_sb):
            with patch("src.routers.health.get_supabase", return_value=mock_sb):
                from src.main import app
                client = TestClient(app)
                resp = client.get("/ready")
                assert resp.status_code == 200
                data = resp.json()
                assert data["supabase"] is True


def test_ready_without_supabase():
    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.limit.return_value.execute.side_effect = Exception("Connection refused")

    with patch("src.storage.supabase.get_supabase", return_value=mock_sb):
        with patch("src.middleware.auth.get_supabase", return_value=mock_sb):
            with patch("src.routers.health.get_supabase", return_value=mock_sb):
                from src.main import app
                client = TestClient(app)
                resp = client.get("/ready")
                assert resp.status_code == 200
                data = resp.json()
                assert data["supabase"] is False
                assert data["status"] == "degraded"
