"""Admin API contracts against an isolated SQL database; no external services."""
from datetime import UTC, datetime, timedelta
from sqlite3 import IntegrityError as SQLiteIntegrityError
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import get_db
from app.main import app
from app.models.schema import (
    AIRequest, AIResponse, DailyReportMetric, FaceAuthenticationLog, FaceProfile,
    InteractionEvent, StaffAccount, StaffSession, Survey, SurveyAnswer, SurveyQuestion, SurveyResponse, User,
    UserSession, Department, Major,
)
from app.services.staff_auth_service import create_staff

PROFILE = {"student_code": "TEST001", "full_name": "Test Student", "email": "student@example.test"}
DEVICE_HEADER = {"X-Admin-Device": "admin-api-test-device-01"}
USER_URL = "/api/v1/users"
MISSING = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def database():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    for model in (User, FaceProfile, UserSession, FaceAuthenticationLog, InteractionEvent,
                  AIRequest, AIResponse, Survey, SurveyQuestion, SurveyResponse, SurveyAnswer, DailyReportMetric,
                  Department, Major, StaffAccount, StaffSession):
        model.__table__.create(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def signed_in(role: str, database) -> TestClient:
    create_staff(database, f"test-{role}", f"Test {role}", role, "test-password")
    database.commit()
    client = TestClient(app, headers=DEVICE_HEADER)
    token = client.post("/api/v1/admin/login", json={"username": f"test-{role}", "password": "test-password"}).json()["data"]["token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest.fixture
def client(database):
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = lambda: database
    try:
        with signed_in("admin", database) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


PROTECTED = [
    ("GET", USER_URL), ("POST", USER_URL),
    ("GET", f"{USER_URL}/{MISSING}"), ("PATCH", f"{USER_URL}/{MISSING}"),
    ("DELETE", f"{USER_URL}/{MISSING}"),
    ("POST", "/api/v1/departments"), ("PATCH", f"/api/v1/departments/{MISSING}"),
    ("POST", f"/api/v1/departments/{MISSING}/majors"), ("PATCH", f"/api/v1/departments/majors/{MISSING}"),
    ("GET", "/api/v1/admin/staff"), ("POST", "/api/v1/admin/staff"), ("GET", "/api/v1/admin/devices"),
    ("POST", "/api/v1/admin/devices"), ("POST", f"/api/v1/admin/devices/{MISSING}/rotate-key"),
    *[("GET", f"/api/v1/{path}") for path in (
        "admin/dashboard", "admin/status", "admin/session",
        "reports/overview", "reports/daily", "reports/sessions",
        "admin/conversations", "admin/surveys", "knowledge/documents",
    )],
]


class NoQueries:
    def __getattr__(self, name):
        pytest.fail("Requests without a bearer token must be rejected before any query")


@pytest.mark.parametrize("method,path", PROTECTED)
@pytest.mark.parametrize("key,code", [
    (None, "ADMIN_CREDENTIALS_REQUIRED"), ("Basic dGVzdDp0ZXN0", "ADMIN_CREDENTIALS_INVALID"),
])
def test_staff_endpoints_reject_missing_credentials_before_queries(method, path, key, code):
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = NoQueries
    try:
        with TestClient(app) as anonymous:
            response = anonymous.request(method, path, headers={"Authorization": key} if key else {}, json={})
        assert response.status_code == 401
        assert response.json()["error"]["code"] == code
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


@pytest.mark.parametrize("method,path", PROTECTED)
def test_unknown_bearer_token_is_rejected(database, method, path):
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = lambda: database
    try:
        with TestClient(app, headers=DEVICE_HEADER) as anonymous:
            response = anonymous.request(method, path, headers={"Authorization": "Bearer forged-token"}, json={})
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "ADMIN_SESSION_EXPIRED"
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


ADMIN_ONLY = [
    ("GET", "/api/v1/admin/staff"),
    ("POST", "/api/v1/admin/staff"), ("GET", "/api/v1/admin/devices"), ("POST", "/api/v1/admin/devices"),
]


def test_no_staff_role_can_erase_a_face_id(admin_staff):
    """Only the visitor, identified at a kiosk, erases their Face ID (consent text 2026-10b)."""
    assert TestClient(app).delete(f"{USER_URL}/{MISSING}/face-profile").status_code in (404, 405)


def test_librarian_reads_dashboards_but_cannot_manage_access(database):
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = lambda: database
    try:
        with signed_in("librarian", database) as librarian:
            assert librarian.get("/api/v1/admin/dashboard").status_code == 200
            assert librarian.get(USER_URL).status_code == 200
            for method, path in ADMIN_ONLY:
                response = librarian.request(method, path, json={})
                assert response.status_code == 403, path
                assert response.json()["error"]["code"] == "ADMIN_ROLE_REQUIRED"
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def test_profile_crud_preserves_biometric_record(client, database):
    created = client.post(USER_URL, json={**PROFILE, "full_name": "  Test Student  "})
    assert created.status_code == 201
    profile = created.json()["data"]
    assert profile["full_name"] == "Test Student"
    user_id = UUID(profile["id"])
    face = FaceProfile(user_id=user_id, face_template_ref="test-reference", enrolled_at=datetime.now(UTC), active=True)
    database.add(face)
    database.commit()
    face_id = face.id
    url = f"{USER_URL}/{user_id}"
    assert client.get(url).json()["data"] == profile
    updated = client.patch(url, json={"faculty": "Test Faculty", "major": "Test Major", "admission_year": 2024})
    assert updated.status_code == 200
    assert updated.json()["data"]["faculty"] == "Test Faculty"
    assert "phone" not in updated.json()["data"]
    assert set(updated.json()["data"]) == set(profile)
    assert "face" not in updated.text
    assert client.delete(url).status_code == 200
    assert client.get(USER_URL).json()["data"]["total"] == 0
    for method in ("get", "patch", "delete"):
        kwargs = {"json": {"full_name": "Changed"}} if method == "patch" else {}
        assert getattr(client, method)(url, **kwargs).status_code == 404
    database.expire_all()
    assert database.get(User, user_id).deleted_at is not None
    assert database.get(User, user_id).account_status == "deactivated"
    retained = database.get(FaceProfile, face_id)
    assert retained.active and retained.face_template_ref == "test-reference"


@pytest.mark.parametrize("field,value", [
    ("full_name", " "), ("full_name", None), ("email", "bad-address"),
    ("phone", "0901234567"),  # phone numbers are no longer collected at all
    ("student_code", "a b"), ("admission_year", 1989),
    ("admission_year", datetime.now(UTC).year + 2), ("admission_year", True),
    ("admission_year", 2024.5), ("faculty", "x" * 151), ("major", "x" * 151),
    ("account_status", "admin"), ("face_template_ref", "forbidden"),
])
def test_invalid_create_and_update_do_not_mutate(client, database, field, value):
    profile = client.post(USER_URL, json=PROFILE).json()["data"]
    response = client.post(USER_URL, json={**PROFILE, field: value})
    assert response.status_code == 422
    response = client.patch(f"{USER_URL}/{profile['id']}", json={field: value})
    assert response.status_code == 422
    assert client.get(f"{USER_URL}/{profile['id']}").json()["data"] == profile
    assert len(database.scalars(select(User)).all()) == 1


def test_empty_patch_and_invalid_identifiers(client):
    assert client.patch(f"{USER_URL}/{MISSING}", json={}).status_code == 422
    assert client.get(f"{USER_URL}/invalid-uuid").status_code == 422
    assert client.get(f"{USER_URL}/{MISSING}").status_code == 404


@pytest.mark.parametrize("field", ["student_code", "email"])
def test_conflicts_include_soft_deleted_profiles(client, field):
    first = client.post(USER_URL, json=PROFILE).json()["data"]
    other = {**PROFILE, "student_code": "TEST002", "email": "second@example.test"}
    second = client.post(USER_URL, json=other).json()["data"]
    candidate = {**other, "student_code": "TEST003", "email": "third@example.test", field: PROFILE[field]}
    assert client.patch(f"{USER_URL}/{second['id']}", json={field: PROFILE[field]}).status_code == 409
    assert client.post(USER_URL, json=candidate).status_code == 409
    assert client.delete(f"{USER_URL}/{first['id']}").status_code == 200
    response = client.post(USER_URL, json=candidate)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == f"{field.upper()}_ALREADY_EXISTS"
    assert client.patch(f"{USER_URL}/{second['id']}", json={field: PROFILE[field]}).status_code == 409


def test_concurrent_unique_conflict_rolls_back_without_exposing_sql(client, database, monkeypatch):
    original_commit = database.commit
    error = SQLiteIntegrityError("private SQL parameters")
    error.sqlite_errorname = "SQLITE_CONSTRAINT_UNIQUE"
    def conflicting_commit():
        raise IntegrityError("private SQL", {"private": "data"}, error)
    monkeypatch.setattr(database, "commit", conflicting_commit)
    response = client.post(USER_URL, json=PROFILE)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "USER_PROFILE_CONFLICT"
    assert "private" not in response.text
    assert not database.new
    monkeypatch.setattr(database, "commit", original_commit)
    assert client.post(USER_URL, json=PROFILE).status_code == 201


def test_search_is_literal_and_pagination_is_bounded(client):
    client.post(USER_URL, json=PROFILE)
    client.post(USER_URL, json={**PROFILE, "student_code": "TEST_02", "email": "second@example.test"})
    assert client.get(USER_URL, params={"search": "_"}).json()["data"]["total"] == 1
    assert client.get(USER_URL, params={"search": "%"}).json()["data"]["total"] == 0
    assert client.get(USER_URL, params={"search": "  student  "}).json()["data"]["total"] == 2
    page = client.get(USER_URL, params={"offset": 1, "limit": 1}).json()["data"]
    assert page["total"] == 2 and len(page["items"]) == 1
    for params in ({"offset": -1}, {"limit": 0}, {"limit": 101}, {"search": "x" * 101}):
        assert client.get(USER_URL, params=params).status_code == 422


def test_dashboard_filters_dates_and_reads_only(client, database):
    now = datetime.now(UTC)
    for moment in (now, now - timedelta(days=15), now + timedelta(days=1)):
        database.add_all([
            UserSession(started_at=moment, identified=True),
            FaceAuthenticationLog(result="SUCCESS", occurred_at=moment, processing_time_ms=200),
            FaceAuthenticationLog(result="UNKNOWN_FACE", occurred_at=moment, processing_time_ms=400),
            InteractionEvent(event_type="CAMERA_ERROR", event_time=moment),
            InteractionEvent(event_type="USER_MESSAGE", event_time=moment),
            AIRequest(request_type="QUESTION", status="completed", created_at=moment),
            SurveyResponse(survey_id=uuid4(), submitted_at=moment),
            DailyReportMetric(report_date=moment.date(), total_sessions=1, total_identified_users=1),
        ])
    database.commit()
    response = client.get("/api/v1/admin/dashboard?days=7")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total_sessions"] == data["identified_users"] == data["questions"] == 1
    assert data["ai_answers"] == data["surveys"] == data["camera_network_errors"] == 1
    assert data["recognition_success_count"] == data["recognition_failure_count"] == 1
    assert data["recognition_success_rate"] == 50
    assert data["avg_wait_seconds"] == 0.3
    assert len(data["daily"]) == 1
    assert data["daily"][0]["sessions"] == data["total_sessions"]
    report = client.get("/api/v1/reports/overview?days=7").json()["data"]
    assert report["total_sessions"] == data["total_sessions"]
    assert report["recognition_success"] == data["recognition_success_count"]
    sessions = client.get("/api/v1/reports/sessions?days=7").json()["data"]
    assert sum(sessions["by_exit_reason"].values()) == data["total_sessions"]
    assert not database.new and not database.dirty and not database.deleted
    assert client.get("/api/v1/admin/dashboard?days=30").json()["data"]["total_sessions"] == 2


def test_empty_dashboard_and_report_validation(client):
    data = client.get("/api/v1/admin/dashboard").json()["data"]
    assert data["recognition_success_rate"] == data["avg_wait_seconds"] == 0
    assert data["daily"] == []
    for endpoint in ("admin/dashboard", "reports/overview", "reports/sessions"):
        for days in (0, 91, "bad"):
            assert client.get(f"/api/v1/{endpoint}?days={days}").status_code == 422
    for period in ("start_date=2026-09-24&end_date=2026-09-01", "start_date=2020-01-01&end_date=2026-01-01"):
        assert client.get(f"/api/v1/reports/daily?{period}").status_code == 422
    assert client.get("/api/v1/reports/overview").status_code == 200
    assert client.get("/api/v1/reports/sessions").status_code == 200
    assert client.get("/api/v1/reports/daily").status_code == 200


def test_dashboard_daily_uses_sessions_without_precomputed_metrics(client, database):
    database.add(UserSession(started_at=datetime.now(UTC), identified=True))
    database.commit()
    data = client.get("/api/v1/admin/dashboard?days=1").json()["data"]
    assert len(data["daily"]) == 1
    assert data["daily"][0]["sessions"] == data["daily"][0]["identified"] == 1
    assert data["total_sessions"] == 1


def test_daily_report_inclusive_period_and_zero_latency(client, database):
    today = datetime.now(UTC).date()
    database.add(DailyReportMetric(report_date=today, avg_ai_response_time_ms=0))
    database.commit()
    response = client.get("/api/v1/reports/daily").json()["data"]
    assert response["period"]["start_date"] == (today - timedelta(days=6)).isoformat()
    assert response["metrics"][0]["avg_ai_response_time_ms"] == 0
    for length, status in ((89, 200), (90, 422)):
        assert client.get("/api/v1/reports/daily", params={
            "start_date": (today - timedelta(days=length)).isoformat(), "end_date": today.isoformat(),
        }).status_code == status


def test_department_and_major_writes_validate_without_breaking_public_lookups(client):
    created = client.post("/api/v1/departments", json={"code": "test", "name": "Test faculty"})
    assert created.status_code == 201
    department = created.json()["data"]
    assert department["code"] == "TEST"
    dept_url = f"/api/v1/departments/{department['id']}"
    major = client.post(f"{dept_url}/majors", json={
        "code": "test-major", "name": "Test major", "department_id": department["id"],
    })
    assert major.status_code == 201
    major_url = f"/api/v1/departments/majors/{major.json()['data']['id']}"
    for url in (dept_url, major_url):
        for invalid in ({}, {"name": None}, {"is_active": None}, {"is_active": "false"}, {"code": "changed"}):
            assert client.patch(url, json=invalid).status_code == 422
        assert client.patch(url, json={"name": "Updated name"}).status_code == 200
    with TestClient(app) as public:
        assert public.get("/api/v1/departments").status_code == 200
        assert public.get(f"{dept_url}/majors").status_code == 200
