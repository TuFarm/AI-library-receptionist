from types import SimpleNamespace
from uuid import UUID
from fastapi.testclient import TestClient

from app.main import app
from app.services.user_service import calculate_student_year

client = TestClient(app)


def test_health_endpoints():
    assert client.get("/health").json()["data"]["status"] == "ok"
    detail = client.get("/api/v1/health").json()["data"]
    assert detail["app_status"] == "ok"
    assert detail["database_status"] in {"connected", "unavailable"}
    assert "database_url" not in detail


def test_database_health_reports_available_and_unavailable(monkeypatch):
    from app.api.v1.routes import health
    monkeypatch.setattr(health, "check_database_connection", lambda: ("connected", None))
    assert client.get("/api/v1/health/db").status_code == 200
    monkeypatch.setattr(health, "check_database_connection", lambda: ("unavailable", "offline"))
    response = client.get("/api/v1/health/db")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"


def test_mock_user_and_student_year():
    user = client.get("/api/v1/users/me/mock").json()["data"]
    assert user["student_code"] == "ITCSIU24092"
    assert user["calculated_student_year"] == calculate_student_year(2024)
    assert calculate_student_year(None, 2026) is None
    assert calculate_student_year(2027, 2026) is None


def test_mock_face_success_and_unknown_identity():
    success = client.post("/api/v1/face/verify/mock", json={"scenario": "SUCCESS"}).json()["data"]
    unknown = client.post("/api/v1/face/verify/mock", json={"scenario": "UNKNOWN_FACE"}).json()["data"]
    assert success["user"]["student_code"] == "ITCSIU24092"
    assert unknown["user"] is None
    assert success["next_state"] == "WELCOME"
    assert unknown["next_state"] == "FACE_UNKNOWN"


def test_kiosk_session_flow(monkeypatch):
    from app.api.v1.routes import kiosk
    session_id = UUID("11111111-1111-1111-1111-111111111111")
    device_id = UUID("22222222-2222-2222-2222-222222222222")
    monkeypatch.setattr(kiosk, "start_session", lambda db, code: (
        SimpleNamespace(id=session_id), SimpleNamespace(id=device_id)))
    monkeypatch.setattr(kiosk, "end_session", lambda db, sid, reason: SimpleNamespace(id=sid, duration_seconds=12))
    started = client.post("/api/v1/kiosk/sessions/start", json={"device_code": "KIOSK_DEV_01", "mode": "kiosk"}).json()["data"]
    assert started["status"] == "active"
    assert started["next_state"] == "FACE_SCANNING"
    ended = client.post(f"/api/v1/kiosk/sessions/{started['session_id']}/end", json={"exit_reason": "COMPLETED"}).json()["data"]
    assert ended["next_state"] == "IDLE"


def test_mock_report_overview(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "admin_username", "test-user")
    monkeypatch.setattr(settings, "admin_password", "test-pass")
    data = client.get("/api/v1/reports/overview/mock", headers={"Authorization": "Basic dGVzdC11c2VyOnRlc3QtcGFzcw=="}).json()["data"]
    assert data["total_sessions"] > 0
    assert data["avg_satisfaction_score"] <= 5


def test_admin_dashboard_exposes_operational_metrics(monkeypatch):
    from app.api.v1.routes import admin
    monkeypatch.setattr(admin.settings, "admin_username", "test-user")
    monkeypatch.setattr(admin.settings, "admin_password", "test-pass")

    class FakeResult:
        def all(self):
            return []

    class FakeDatabase:
        def __init__(self):
            self.values = iter([10, 4, 20, 18, 5, 8, 6, 250, 3])

        def scalar(self, _query):
            return next(self.values)

        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

        def execute(self, _query):
            return FakeResult()

    app.dependency_overrides[admin.get_db] = lambda: FakeDatabase()
    try:
        data = client.get("/api/v1/admin/dashboard", headers={"Authorization": "Basic dGVzdC11c2VyOnRlc3QtcGFzcw=="}).json()["data"]
    finally:
        app.dependency_overrides.pop(admin.get_db, None)

    assert data["total_sessions"] == 10
    assert data["recognition_success_count"] == 6
    assert data["recognition_failure_count"] == 2
    assert data["recognition_success_rate"] == 75.0
    assert data["avg_wait_seconds"] == 0.25
    assert data["camera_network_errors"] == 3
