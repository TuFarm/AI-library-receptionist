"""Face ID erasure: the visitor at a kiosk, or an admin at the desk; every erasure is audited."""
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import app
from app.models.schema import FaceIdErasure, FaceProfile, User, UserSession
from tests.conftest import TEST_DEVICE_ID

USERS = "/api/v1/users"
VALID = {"reason": "Kiosk không còn nhận ra, SV mang thẻ đến quầy", "student_present": True}


def enrolled_user(db, name="Người A"):
    user = User(full_name=name, user_type="STUDENT", account_status="ACTIVE",
                face_consent_at=datetime.now(UTC), face_consent_version="2026-10c")
    db.add(user)
    db.flush()
    db.add(FaceProfile(user_id=user.id, face_template_ref="ref", enrolled_at=datetime.now(UTC), active=True))
    db.commit()
    return user


def profiles(db, user):
    return db.scalar(select(func.count()).select_from(FaceProfile).where(FaceProfile.user_id == user.id))


def test_admin_erases_at_the_desk_and_the_erasure_is_logged(use_db, admin_staff):
    user = enrolled_user(use_db)
    response = TestClient(app).post(f"{USERS}/{user.id}/face-id-erasures", json=VALID)
    assert response.status_code == 200 and response.json()["data"]["deleted_profiles"] == 1
    use_db.refresh(user)
    assert profiles(use_db, user) == 0 and user.face_consent_at is None
    log = use_db.scalar(select(FaceIdErasure))
    assert (log.source, log.staff_username, log.reason, log.deleted_profiles) == ("ADMIN", "test-admin", VALID["reason"], 1)
    history = TestClient(app).get(f"{USERS}/{user.id}/face-id-erasures").json()["data"]
    assert [row["source"] for row in history] == ["ADMIN"] and history[0]["staff_username"] == "test-admin"


@pytest.mark.parametrize("body", [
    {"student_present": True},
    {"reason": "  ab ", "student_present": True},
    {"reason": VALID["reason"], "student_present": False},
    {"reason": VALID["reason"]},
])
def test_admin_erasure_needs_a_reason_and_the_student_present(use_db, admin_staff, body):
    user = enrolled_user(use_db)
    assert TestClient(app).post(f"{USERS}/{user.id}/face-id-erasures", json=body).status_code == 422
    assert profiles(use_db, user) == 1 and use_db.scalar(select(func.count()).select_from(FaceIdErasure)) == 0


def test_erasing_without_a_face_id_is_refused(use_db, admin_staff):
    user = User(full_name="Chưa đăng ký", user_type="STUDENT", account_status="ACTIVE")
    use_db.add(user)
    use_db.commit()
    response = TestClient(app).post(f"{USERS}/{user.id}/face-id-erasures", json=VALID)
    assert response.status_code == 409 and response.json()["error"]["code"] == "NO_FACE_ID"


def test_kiosk_self_erasure_is_logged_with_the_device(use_db):
    user = enrolled_user(use_db)
    session = UserSession(device_id=TEST_DEVICE_ID, user_id=user.id, identified=True, started_at=datetime.now(UTC))
    use_db.add(session)
    use_db.commit()
    assert TestClient(app).delete(f"/api/v1/kiosk/sessions/{session.id}/face-profile").status_code == 200
    log = use_db.scalar(select(FaceIdErasure))
    assert (log.source, log.device_id, log.staff_username) == ("KIOSK", TEST_DEVICE_ID, None)


def test_user_list_shows_who_has_a_face_id_without_template_data(use_db, admin_staff):
    enrolled = enrolled_user(use_db, "Có Face ID")
    use_db.add(User(full_name="Không có", user_type="STUDENT", account_status="ACTIVE"))
    use_db.commit()
    response = TestClient(app).get(USERS)
    items = {item["full_name"]: item for item in response.json()["data"]["items"]}
    assert items["Có Face ID"]["has_face_id"] is True and items["Không có"]["has_face_id"] is False
    assert "ref" not in response.text and str(enrolled.id) in response.text
