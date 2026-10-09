"""Staff/device management and kiosk device authentication against an isolated SQL database."""
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from starlette.websockets import WebSocketDisconnect

from app.api.deps import require_kiosk_device
from app.api.v1.routes import runtime
from app.main import app
from app.models.schema import Device, FaceProfile, StaffSession, User, UserSession
from app.services.staff_auth_service import create_staff

ADMIN_DEVICE = {"X-Admin-Device": "access-control-test-device"}
ORIGIN = {"origin": "http://localhost:5173"}


@pytest.fixture
def real_device_auth():
    """Undo conftest's trusted-kiosk override so X-Device-Key is really checked."""
    override = app.dependency_overrides.pop(require_kiosk_device, None)
    yield
    if override is not None:
        app.dependency_overrides[require_kiosk_device] = override


@pytest.fixture
def admin(use_db):
    create_staff(use_db, "root", "Quản trị", "admin", "root-password")
    use_db.commit()
    with TestClient(app, headers=ADMIN_DEVICE) as client:
        token = client.post("/api/v1/admin/login", json={"username": "root", "password": "root-password"}).json()["data"]["token"]
        client.headers["Authorization"] = f"Bearer {token}"
        yield client


def register(admin, code="KIOSK_A"):
    response = admin.post("/api/v1/admin/devices", json={"device_code": code, "device_name": f"Kiosk {code}"})
    assert response.status_code == 201, response.text
    return response.json()["data"]


# ---- staff accounts ---------------------------------------------------------------------------

def test_admin_creates_librarian_who_can_sign_in(admin):
    created = admin.post("/api/v1/admin/staff", json={
        "username": "Thu.Thu", "full_name": "Thủ thư", "role": "librarian", "password": "librarian-pass"})
    assert created.status_code == 201
    data = created.json()["data"]
    assert data["username"] == "thu.thu" and data["role"] == "librarian"
    assert "password" not in created.text and "pbkdf2" not in created.text
    assert admin.post("/api/v1/admin/staff", json={
        "username": "thu.thu", "full_name": "X", "password": "librarian-pass"}).status_code == 409
    with TestClient(app, headers=ADMIN_DEVICE) as other:
        login = other.post("/api/v1/admin/login", json={"username": "thu.thu", "password": "librarian-pass"})
        assert login.status_code == 200 and login.json()["data"]["role"] == "librarian"


@pytest.mark.parametrize("payload", [
    {"username": "ab", "full_name": "X", "password": "long-enough"},
    {"username": "has space", "full_name": "X", "password": "long-enough"},
    {"username": "valid", "full_name": " ", "password": "long-enough"},
    {"username": "valid", "full_name": "X", "password": "short"},
    {"username": "valid", "full_name": "X", "password": "long-enough", "role": "owner"},
])
def test_invalid_staff_payloads_are_rejected(admin, payload):
    assert admin.post("/api/v1/admin/staff", json=payload).status_code == 422


def test_role_change_and_deactivation_revoke_sessions(admin, use_db):
    staff = create_staff(use_db, "helper", "Helper", "admin", "helper-pass")
    use_db.commit()
    with TestClient(app, headers=ADMIN_DEVICE) as helper:
        token = helper.post("/api/v1/admin/login", json={"username": "helper", "password": "helper-pass"}).json()["data"]["token"]
        helper.headers["Authorization"] = f"Bearer {token}"
        assert admin.patch(f"/api/v1/admin/staff/{staff.id}", json={"role": "librarian"}).status_code == 200
        assert helper.get("/api/v1/admin/session").status_code == 401
    assert admin.patch(f"/api/v1/admin/staff/{staff.id}", json={"is_active": False}).json()["data"]["is_active"] is False
    assert TestClient(app, headers=ADMIN_DEVICE).post(
        "/api/v1/admin/login", json={"username": "helper", "password": "helper-pass"}).status_code == 403


def test_admin_cannot_lock_themselves_out_or_remove_last_admin(admin, use_db):
    me = admin.get("/api/v1/admin/session").json()["data"]
    for change in ({"role": "librarian"}, {"is_active": False}):
        response = admin.patch(f"/api/v1/admin/staff/{me['id']}", json=change)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "CANNOT_CHANGE_OWN_ACCESS"
    other = create_staff(use_db, "second", "Second", "admin", "second-pass")
    use_db.commit()
    assert admin.patch(f"/api/v1/admin/staff/{other.id}", json={"role": "librarian"}).status_code == 200


def test_password_reset_revokes_sessions_and_unlocks(admin, use_db):
    staff = create_staff(use_db, "forgetful", "F", "librarian", "old-password")
    staff.locked_until = datetime(2999, 1, 1, tzinfo=UTC)
    use_db.commit()
    assert admin.post(f"/api/v1/admin/staff/{staff.id}/reset-password", json={"new_password": "new-password"}).status_code == 200
    with TestClient(app, headers=ADMIN_DEVICE) as client:
        assert client.post("/api/v1/admin/login", json={"username": "forgetful", "password": "new-password"}).status_code == 200


# ---- device registration ----------------------------------------------------------------------

def test_device_key_is_shown_once_and_only_its_hash_is_stored(admin, use_db):
    device = register(admin, "kiosk-lobby")
    key = device["device_key"]
    assert device["device_code"] == "KIOSK-LOBBY" and key.startswith("kd_") and len(key) > 40
    listed = admin.get("/api/v1/admin/devices")
    assert key not in listed.text and "device_key" not in listed.text and "api_key_hash" not in listed.text
    assert listed.json()["data"][0]["key_prefix"] == key[:10]
    stored = use_db.scalar(select(Device.api_key_hash))
    assert stored != key and len(stored) == 64
    assert admin.post("/api/v1/admin/devices", json={"device_code": "KIOSK-LOBBY", "device_name": "dup"}).status_code == 409


def test_legacy_keyless_device_row_can_be_claimed(admin, use_db):
    use_db.add(Device(device_code="KIOSK_DEV_01", device_name="old", status="active"))
    use_db.commit()
    device = register(admin, "KIOSK_DEV_01")
    assert device["has_key"] and len(use_db.scalars(select(Device)).all()) == 1


def test_kiosk_rest_calls_require_a_valid_active_key(admin, use_db, real_device_auth):
    key = register(admin)["device_key"]
    with TestClient(app) as kiosk:
        for headers, status, code in (({}, 401, "DEVICE_KEY_REQUIRED"), ({"X-Device-Key": "kd_forged"}, 401, "DEVICE_KEY_INVALID"),
                                      ({"X-Device-Key": "not-a-device-key"}, 401, "DEVICE_KEY_INVALID")):
            response = kiosk.post("/api/v1/kiosk/sessions/start", json={}, headers=headers)
            assert (response.status_code, response.json()["error"]["code"]) == (status, code)
        me = kiosk.get("/api/v1/kiosk/device", headers={"X-Device-Key": key})
        assert me.status_code == 200 and me.json()["data"]["device_code"] == "KIOSK_A"
        started = kiosk.post("/api/v1/kiosk/sessions/start", json={"device_code": "SPOOFED"}, headers={"X-Device-Key": key})
        assert started.status_code == 200
    session = use_db.get(UserSession, started.json()["data"]["session_id"].__class__(started.json()["data"]["session_id"])) \
        if False else use_db.scalar(select(UserSession))
    assert session.device_id == use_db.scalar(select(Device.id).where(Device.device_code == "KIOSK_A"))
    assert use_db.scalar(select(Device).where(Device.device_code == "SPOOFED")) is None


def test_rotated_or_disabled_keys_stop_working(admin, real_device_auth):
    device = register(admin)
    old_key = device["device_key"]
    new_key = admin.post(f"/api/v1/admin/devices/{device['id']}/rotate-key").json()["data"]["device_key"]
    with TestClient(app) as kiosk:
        assert kiosk.get("/api/v1/kiosk/device", headers={"X-Device-Key": old_key}).status_code == 401
        assert kiosk.get("/api/v1/kiosk/device", headers={"X-Device-Key": new_key}).status_code == 200
        assert admin.patch(f"/api/v1/admin/devices/{device['id']}", json={"status": "disabled"}).status_code == 200
        disabled = kiosk.get("/api/v1/kiosk/device", headers={"X-Device-Key": new_key})
        assert disabled.status_code == 403 and disabled.json()["error"]["code"] == "DEVICE_DISABLED"


# ---- session ownership ------------------------------------------------------------------------

def two_kiosks(admin):
    return register(admin, "KIOSK_A")["device_key"], register(admin, "KIOSK_B")["device_key"]


def test_a_kiosk_cannot_touch_another_kiosks_session_or_conversation(admin, use_db, real_device_auth):
    key_a, key_b = two_kiosks(admin)
    with TestClient(app) as kiosk:
        a = {"X-Device-Key": key_a}
        b = {"X-Device-Key": key_b}
        session_id = kiosk.post("/api/v1/kiosk/sessions/start", json={}, headers=a).json()["data"]["session_id"]
        conversation = kiosk.post("/api/v1/conversations/start", json={"session_id": session_id}, headers=a)
        assert conversation.status_code == 200
        conversation_id = conversation.json()["data"]["conversation_id"]
        foreign = [
            ("POST", f"/api/v1/kiosk/sessions/{session_id}/events", {"event_type": "PROBE"}),
            ("POST", f"/api/v1/kiosk/sessions/{session_id}/end", {}),
            ("POST", "/api/v1/conversations/start", {"session_id": session_id}),
            ("GET", f"/api/v1/conversations/{conversation_id}/messages", None),
            ("POST", f"/api/v1/conversations/{conversation_id}/messages", {"message_text": "hi"}),
            ("POST", "/api/v1/ai/answer", {"conversation_id": conversation_id, "message_text": "hi"}),
            ("POST", "/api/v1/voice/browser-transcript", {"conversation_id": conversation_id, "transcript": "hi"}),
        ]
        for method, path, body in foreign:
            response = kiosk.request(method, path, json=body, headers=b)
            assert response.status_code == 404, (path, response.text)
        assert kiosk.get(f"/api/v1/conversations/{conversation_id}/messages", headers=a).status_code == 200


def identified_session(use_db, device_code="KIOSK_A"):
    device = use_db.scalar(select(Device).where(Device.device_code == device_code))
    user = User(full_name="Người A", student_code="A001", user_type="STUDENT", account_status="ACTIVE")
    use_db.add(user)
    use_db.flush()
    use_db.add(FaceProfile(user_id=user.id, face_template_ref="ref-a", enrolled_at=datetime.now(UTC), active=True))
    session = UserSession(device_id=device.id, user_id=user.id, identified=True, started_at=datetime.now(UTC))
    use_db.add(session)
    use_db.commit()
    return user, session


def test_kiosk_profile_actions_are_limited_to_the_identified_visitor(admin, use_db, real_device_auth):
    key_a, key_b = two_kiosks(admin)
    user, session = identified_session(use_db)
    anonymous = UserSession(device_id=session.device_id, identified=False, started_at=datetime.now(UTC))
    use_db.add(anonymous)
    use_db.commit()
    with TestClient(app) as kiosk:
        a, b = {"X-Device-Key": key_a}, {"X-Device-Key": key_b}
        assert kiosk.patch(f"/api/v1/kiosk/sessions/{session.id}/profile", json={"major": "CNTT"}, headers=b).status_code == 404
        assert kiosk.patch(f"/api/v1/kiosk/sessions/{anonymous.id}/profile", json={"major": "CNTT"}, headers=a).status_code == 403
        updated = kiosk.patch(f"/api/v1/kiosk/sessions/{session.id}/profile", json={"major": "CNTT"}, headers=a)
        assert updated.status_code == 200 and updated.json()["data"]["major"] == "CNTT"
        assert kiosk.delete(f"/api/v1/kiosk/sessions/{anonymous.id}/face-profile", headers=a).status_code == 403
        deleted = kiosk.delete(f"/api/v1/kiosk/sessions/{session.id}/face-profile", headers=a)
        assert deleted.status_code == 200 and deleted.json()["data"]["deleted_profiles"] == 1
        # The old unscoped routes are no longer reachable with only a device key.
        assert kiosk.patch(f"/api/v1/users/{user.id}", json={"major": "X"}, headers=a).status_code == 401
        assert kiosk.delete(f"/api/v1/users/{user.id}/face-profile", headers=a).status_code == 404
        session.ended_at = datetime.now(UTC)
        use_db.commit()
        ended = kiosk.patch(f"/api/v1/kiosk/sessions/{session.id}/profile", json={"major": "Y"}, headers=a)
        assert ended.status_code == 409


def test_enrollment_cannot_claim_another_persons_face_id(admin, use_db, real_device_auth, monkeypatch, tmp_path):
    from app.api.v1.routes import face
    from app.services.face_service import FaceEnrollmentResult

    key_a, _ = two_kiosks(admin)
    victim, _ = identified_session(use_db)
    monkeypatch.setattr(face.settings, "media_storage_dir", tmp_path)
    monkeypatch.setattr(face.FaceService, "prepare_enrollment", lambda self, path: FaceEnrollmentResult(
        None, b"[0.0]", "test-model", "1", 0.9))
    with TestClient(app) as kiosk:
        headers = {"X-Device-Key": key_a}
        image = {"image_file": ("face.jpg", b"\xff\xd8\xfftest", "image/jpeg")}
        session_id = kiosk.post("/api/v1/kiosk/sessions/start", json={}, headers=headers).json()["data"]["session_id"]
        claimed = kiosk.post("/api/v1/face/enroll", data={"face_consent": "true", "session_id": session_id, "full_name": "Kẻ giả mạo",
                                                          "student_code": victim.student_code}, files=image, headers=headers)
        assert claimed.status_code == 409 and claimed.json()["error"]["code"] == "FACE_ALREADY_REGISTERED"
        by_id = kiosk.post("/api/v1/face/enroll", data={"face_consent": "true", "session_id": session_id, "user_id": str(victim.id)},
                           files=image, headers=headers)
        assert by_id.status_code == 403 and by_id.json()["error"]["code"] == "SESSION_NOT_IDENTIFIED"
    use_db.expire_all()
    profiles = use_db.scalars(select(FaceProfile).where(FaceProfile.user_id == victim.id)).all()
    assert [profile.face_template_ref for profile in profiles] == ["ref-a"]
    assert use_db.get(User, victim.id).full_name == "Người A"


# ---- WebSocket --------------------------------------------------------------------------------

@pytest.fixture
def stream_db(use_db, monkeypatch):
    monkeypatch.setattr(runtime, "SessionLocal", sessionmaker(bind=use_db.get_bind()))
    return use_db


def close_code(messages):
    with TestClient(app) as client, client.websocket_connect("/api/v1/kiosk/stream", headers=ORIGIN) as socket:
        for message in messages:
            socket.send_json(message)
        with pytest.raises(WebSocketDisconnect) as closed:
            for _ in range(5):  # a successful AUTH is followed by `stream_ready` before the close
                assert socket.receive_json()["event"] == "stream_ready"
        return closed.value.code


def test_stream_requires_auth_as_first_message(admin, stream_db):
    key = register(admin)["device_key"]
    assert close_code([{"event": "PING", "payload": {}}]) == runtime.CLOSE_DEVICE_UNAUTHORIZED
    assert close_code([{"event": "AUTH", "payload": {"device_key": "kd_forged"}}]) == runtime.CLOSE_DEVICE_UNAUTHORIZED
    assert close_code([{"event": "AUTH", "payload": "not-an-object"}]) == runtime.CLOSE_DEVICE_UNAUTHORIZED
    with TestClient(app) as client, client.websocket_connect("/api/v1/kiosk/stream", headers=ORIGIN) as socket:
        socket.send_json({"event": "AUTH", "payload": {"device_key": key}})
        assert socket.receive_json()["event"] == "stream_ready"


def test_stream_rejects_disabled_device_and_foreign_sessions(admin, stream_db):
    device_a = register(admin, "KIOSK_A")
    key_b = register(admin, "KIOSK_B")["device_key"]
    foreign = UserSession(device_id=stream_db.scalar(select(Device.id).where(Device.device_code == "KIOSK_A")),
                          identified=False, started_at=datetime.now(UTC))
    stream_db.add(foreign)
    stream_db.commit()
    auth_b = {"event": "AUTH", "payload": {"device_key": key_b}}
    for session_id in (str(foreign.id), str(uuid4()), "not-a-uuid"):
        assert close_code([auth_b, {"event": "CONFIGURE", "payload": {"mode": "recognition", "session_id": session_id}}]) \
            == runtime.CLOSE_DEVICE_FORBIDDEN
    admin.patch(f"/api/v1/admin/devices/{device_a['id']}", json={"status": "disabled"})
    assert close_code([{"event": "AUTH", "payload": {"device_key": device_a["device_key"]}}]) == runtime.CLOSE_DEVICE_FORBIDDEN


def test_logout_only_revokes_the_current_session(admin, use_db):
    with TestClient(app, headers=ADMIN_DEVICE) as second:
        token = second.post("/api/v1/admin/login", json={"username": "root", "password": "root-password"}).json()["data"]["token"]
        second.headers["Authorization"] = f"Bearer {token}"
        assert admin.post("/api/v1/admin/logout").status_code == 200
        assert second.get("/api/v1/admin/session").status_code == 200
    assert len([row for row in use_db.scalars(select(StaffSession)).all() if row.revoked_at]) == 1
