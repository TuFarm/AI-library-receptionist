"""A retried POST /face/enroll (same enrollment_id) replays the first result instead of enrolling twice."""
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.deps import require_kiosk_device
from app.main import app
from app.models.schema import FaceEnrollmentRequest, FaceProfile, InteractionEvent, User
from app.services.face_service import FaceEnrollmentResult
from app.services.user_service import delete_face_profiles

JPEG = ("face.jpg", b"\xff\xd8\xffsafe-test", "image/jpeg")


@pytest.fixture
def analysed(monkeypatch, tmp_path, use_db):
    from app.api.v1.routes import face
    calls = []
    monkeypatch.setattr(face.settings, "media_storage_dir", tmp_path)

    def prepare(_self, _path):
        calls.append(_path)
        return FaceEnrollmentResult(None, b"[1.0, 0.0]", "opencv-sface-128d", "2021dec", 0.9)

    monkeypatch.setattr(face.FaceService, "prepare_enrollment", prepare)
    return calls


def enroll(key, name="Người A"):
    data = {"face_consent": "true", "full_name": name}
    if key is not None:
        data["enrollment_id"] = str(key)
    return TestClient(app).post("/api/v1/face/enroll", data=data, files={"image_file": JPEG})


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_retry_with_the_same_key_replays_without_a_second_enrollment(analysed, use_db):
    key = uuid4()
    first, second = enroll(key), enroll(key)
    assert first.status_code == second.status_code == 200
    assert first.json()["data"]["face_profile_id"] == second.json()["data"]["face_profile_id"]
    assert first.json()["data"]["user_id"] == second.json()["data"]["user_id"]
    assert len(analysed) == 1  # the replay never saved or analysed the image again
    assert count(use_db, User) == count(use_db, FaceProfile) == count(use_db, FaceEnrollmentRequest) == 1
    assert use_db.scalar(select(func.count()).where(InteractionEvent.event_type == "FACE_ENROLLED")) == 1


def test_a_new_key_is_a_new_enrollment(analysed, use_db):
    assert enroll(uuid4(), "Người A").status_code == enroll(uuid4(), "Người B").status_code == 200
    assert count(use_db, FaceProfile) == 2 and len(analysed) == 2


def test_requests_without_a_key_still_work(analysed, use_db):
    assert enroll(None).status_code == 200
    assert count(use_db, FaceEnrollmentRequest) == 0


def test_the_same_key_from_another_kiosk_is_rejected(analysed, use_db):
    key = uuid4()
    assert enroll(key).status_code == 200
    other = SimpleNamespace(id=UUID("0d0d0d0d-0000-4000-8000-000000000002"), device_code="KIOSK_OTHER",
                            status="active", deleted_at=None)
    app.dependency_overrides[require_kiosk_device] = lambda: other
    response = enroll(key)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ENROLLMENT_ID_CONFLICT"
    assert len(analysed) == 1 and count(use_db, FaceProfile) == 1


def test_an_erased_face_id_is_never_replayed_as_success(analysed, use_db):
    key = uuid4()
    user_id = UUID(enroll(key).json()["data"]["user_id"])
    delete_face_profiles(use_db, user_id)
    response = enroll(key)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ENROLLMENT_ALREADY_PROCESSED"
    assert count(use_db, FaceProfile) == 0 and len(analysed) == 1


@pytest.mark.parametrize("face,voice,face_warning,voice_warning", [
    ("local_opencv", "gemini", "liveness", "Google Gemini"),
    ("local_opencv", "browser", "liveness", "Chrome gửi âm thanh tới Google"),
])
def test_status_page_discloses_liveness_gap_and_where_voice_goes(
        use_db, admin_staff, monkeypatch, face, voice, face_warning, voice_warning):
    from app.core.config import settings
    monkeypatch.setattr(settings, "face_provider", face)
    monkeypatch.setattr(settings, "voice_provider", voice)
    rows = {row["module"]: row for row in TestClient(app).get("/api/v1/admin/status").json()["data"]}
    assert face_warning in rows["FaceID"]["warning"]
    assert voice_warning in rows["Voice"]["warning"]
