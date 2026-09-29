from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models.schema import StaffAccount, StaffSession
from app.services import staff_auth_service as auth

DEVICE = "test-browser-device-123456"
LOGIN = "/api/v1/admin/login"
SESSION = "/api/v1/admin/session"


@pytest.fixture
def client(use_db):
    auth.create_staff(use_db, "staff", "Nhân viên", "admin", "initial-password")
    use_db.commit()
    with TestClient(app, headers={"X-Admin-Device": DEVICE}) as client:
        yield client


def login(client, password="initial-password", username="staff"):
    response = client.post(LOGIN, json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    session = response.json()["data"]
    client.headers["Authorization"] = f"Bearer {session['token']}"
    return session


def at(monkeypatch, moment):
    monkeypatch.setattr(auth, "_now", lambda: moment)


def test_session_persists_and_expires_at_fifteen_minutes(client, monkeypatch):
    now = datetime.now(UTC).replace(microsecond=0)
    at(monkeypatch, now)
    session = login(client)
    assert session["expires_at"] == int(now.timestamp()) + 900
    assert session["role"] == "admin" and session["username"] == "staff"
    with TestClient(app, headers=dict(client.headers)) as reopened:
        assert reopened.get(SESSION).status_code == 200
    at(monkeypatch, now + timedelta(seconds=899))
    assert client.get(SESSION).status_code == 200
    at(monkeypatch, now + timedelta(seconds=900))
    assert client.get(SESSION).status_code == 401


def test_other_device_ip_or_browser_cannot_reuse_session(client):
    login(client)
    assert client.get(SESSION, headers={"X-Admin-Device": "another-device-123456"}).status_code == 401
    assert client.get(SESSION, headers={"User-Agent": "different-browser"}).status_code == 401
    with TestClient(app, headers=dict(client.headers), client=("192.0.2.44", 50000)) as other_ip:
        assert other_ip.get(SESSION).status_code == 401
    assert client.get(SESSION).status_code == 200


def test_logout_revokes_token(client):
    login(client)
    assert client.post("/api/v1/admin/logout").status_code == 200
    assert client.get(SESSION).status_code == 401


def test_only_token_digest_is_stored(client, use_db):
    session = login(client)
    stored = use_db.scalars(select(StaffSession.token_hash)).all()
    assert session["token"] not in stored
    assert stored == [auth.sha256_hex(session["token"])]


def test_password_change_persists_hash_and_revokes_all_sessions(client, use_db):
    first = login(client)
    login(client)
    response = client.post("/api/v1/admin/password", json={"current_password": "initial-password", "new_password": "mật-khẩu-mới-123"})
    assert response.status_code == 200
    assert client.get(SESSION).status_code == 401
    client.headers["Authorization"] = f"Bearer {first['token']}"
    assert client.get(SESSION).status_code == 401
    assert client.post(LOGIN, json={"username": "staff", "password": "initial-password"}).status_code == 403
    login(client, "mật-khẩu-mới-123")
    assert client.get(SESSION).status_code == 200
    stored = use_db.scalar(select(StaffAccount.password_hash))
    assert stored.startswith("pbkdf2_sha256$")
    assert "initial-password" not in stored and "mật-khẩu-mới-123" not in stored


@pytest.mark.parametrize("new,status", [("short", 422), (" " * 8, 422), ("initial-password", 422)])
def test_password_validation_keeps_session_valid(client, new, status):
    login(client)
    assert client.post("/api/v1/admin/password", json={"current_password": "initial-password", "new_password": new}).status_code == status
    assert client.get(SESSION).status_code == 200


def test_wrong_current_password_does_not_change_account(client):
    login(client)
    assert client.post("/api/v1/admin/password", json={"current_password": "wrong-password", "new_password": "different-password"}).status_code == 403
    assert client.get(SESSION).status_code == 200
    login(client)


def test_login_needs_device_and_valid_fields(client):
    for payload in ({}, {"username": "", "password": "x"}, {"username": "staff", "password": ""}):
        assert client.post(LOGIN, json=payload).status_code == 422
    client.headers.pop("X-Admin-Device")
    assert client.post(LOGIN, json={"username": "staff", "password": "initial-password"}).status_code == 422


def test_username_is_case_insensitive_and_unknown_user_is_denied(client):
    login(client, username="  STAFF ")
    response = client.post(LOGIN, json={"username": "nobody", "password": "initial-password"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ADMIN_ACCESS_DENIED"


def test_repeated_failures_lock_the_account_temporarily(client, monkeypatch):
    now = datetime.now(UTC)
    at(monkeypatch, now)
    for _ in range(5):
        assert client.post(LOGIN, json={"username": "staff", "password": "wrong-password"}).status_code == 403
    locked = client.post(LOGIN, json={"username": "staff", "password": "initial-password"})
    assert locked.status_code == 429
    assert locked.json()["error"]["code"] == "ADMIN_ACCOUNT_LOCKED"
    at(monkeypatch, now + timedelta(minutes=15, seconds=1))
    login(client)


def test_success_resets_failure_counter(client, use_db):
    for _ in range(4):
        client.post(LOGIN, json={"username": "staff", "password": "wrong-password"})
    login(client)
    use_db.expire_all()
    assert use_db.scalar(select(StaffAccount.failed_login_count)) == 0


def test_deactivated_account_loses_existing_sessions(client, use_db):
    login(client)
    staff = use_db.scalar(select(StaffAccount))
    staff.is_active = False
    use_db.commit()
    assert client.get(SESSION).status_code == 401
    assert client.post(LOGIN, json={"username": "staff", "password": "initial-password"}).status_code == 403
