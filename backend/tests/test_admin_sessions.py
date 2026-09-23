import time

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services import admin_auth_service as auth

DEVICE = "test-browser-device-123456"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "admin_username", "staff")
    monkeypatch.setattr(settings, "admin_password", "initial-password")
    with TestClient(app, headers={"X-Admin-Device": DEVICE}) as client:
        yield client


def login(client, password="initial-password"):
    response = client.post("/api/v1/admin/login", json={"username": "staff", "password": password})
    assert response.status_code == 200
    session = response.json()["data"]
    client.headers["Authorization"] = f"Bearer {session['token']}"
    return session


def test_session_persists_and_expires_at_fifteen_minutes(client, monkeypatch):
    now = int(time.time())
    monkeypatch.setattr(auth.time, "time", lambda: now)
    session = login(client)
    assert session["expires_at"] == now + 900
    with TestClient(app, headers=dict(client.headers)) as reopened:
        assert reopened.get("/api/v1/admin/session").status_code == 200
    monkeypatch.setattr(auth.time, "time", lambda: now + 899)
    assert client.get("/api/v1/admin/session").status_code == 200
    monkeypatch.setattr(auth.time, "time", lambda: now + 900)
    assert client.get("/api/v1/admin/session").status_code == 401


def test_other_device_ip_or_browser_cannot_reuse_session(client):
    login(client)
    assert client.get("/api/v1/admin/session", headers={"X-Admin-Device": "another-device-123456"}).status_code == 401
    assert client.get("/api/v1/admin/session", headers={"User-Agent": "different-browser"}).status_code == 401
    with TestClient(app, headers=dict(client.headers), client=("192.0.2.44", 50000)) as other_ip:
        assert other_ip.get("/api/v1/admin/session").status_code == 401
    assert client.get("/api/v1/admin/session").status_code == 200


def test_logout_revokes_token(client):
    login(client)
    assert client.post("/api/v1/admin/logout").status_code == 200
    assert client.get("/api/v1/admin/session").status_code == 401


def test_password_change_persists_hash_and_revokes_all_sessions(client):
    first = login(client)
    login(client)
    response = client.post("/api/v1/admin/password", json={"current_password": "initial-password", "new_password": "mật-khẩu-mới-123"})
    assert response.status_code == 200
    assert client.get("/api/v1/admin/session").status_code == 401
    client.headers["Authorization"] = f"Bearer {first['token']}"
    assert client.get("/api/v1/admin/session").status_code == 401
    assert client.post("/api/v1/admin/login", json={"username": "staff", "password": "initial-password"}).status_code == 403
    login(client, "mật-khẩu-mới-123")
    assert client.get("/api/v1/admin/session").status_code == 200
    raw = settings.admin_auth_store_path.read_bytes()
    assert b"initial-password" not in raw
    assert "mật-khẩu-mới-123".encode() not in raw


@pytest.mark.parametrize("new,status", [("short", 422), (" " * 8, 422), ("initial-password", 422)])
def test_password_validation_keeps_session_valid(client, new, status):
    login(client)
    assert client.post("/api/v1/admin/password", json={"current_password": "initial-password", "new_password": new}).status_code == status
    assert client.get("/api/v1/admin/session").status_code == 200


def test_wrong_current_password_does_not_change_account(client):
    login(client)
    assert client.post("/api/v1/admin/password", json={"current_password": "wrong-password", "new_password": "different-password"}).status_code == 403
    assert client.get("/api/v1/admin/session").status_code == 200
    login(client)


def test_login_needs_device_and_valid_fields(client):
    for payload in ({}, {"username": "", "password": "x"}, {"username": "staff", "password": ""}):
        assert client.post("/api/v1/admin/login", json=payload).status_code == 422
    client.headers.pop("X-Admin-Device")
    assert client.post("/api/v1/admin/login", json={"username": "staff", "password": "initial-password"}).status_code == 422
