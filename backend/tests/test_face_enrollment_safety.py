from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4
import json
import os

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.main import app
from app.services import face_service
from app.services.face_service import (
    FaceProviderUnavailable, FaceService, MultipleFacesDetectedError, NoFaceDetectedError,
)


class FakeLocalLibrary:
    def __init__(self, count: int):
        self.count = count

    @staticmethod
    def load_image_file(_path):
        return object()

    def face_locations(self, _image, model="hog"):
        return [(0, 10, 10, 0)] * self.count

    def face_encodings(self, _image, known_face_locations):
        return [[0.1] * 128 for _ in known_face_locations]


@pytest.mark.parametrize("face_count, error", [
    (0, NoFaceDetectedError),
    (1, None),
    (2, MultipleFacesDetectedError),
])
def test_local_enrollment_detector_requires_exactly_one_face(monkeypatch, tmp_path: Path, face_count, error):
    image = tmp_path / "upload.jpg"
    image.write_bytes(b"not logged or persisted")
    monkeypatch.setattr(face_service.settings, "face_provider", "local")
    monkeypatch.setattr(face_service, "_load_local_library", lambda: FakeLocalLibrary(face_count))
    if error:
        with pytest.raises(error):
            FaceService().validate_enrollment_image(image)
    else:
        assert len(FaceService().validate_enrollment_image(image)) == 128


def test_mock_provider_cannot_claim_safe_or_real_identity_enrollment(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(face_service.settings, "face_provider", "mock")
    image = tmp_path / "upload.jpg"
    image.write_bytes(b"test")
    with pytest.raises(FaceProviderUnavailable, match="chỉ dành cho kiểm thử"):
        FaceService().validate_enrollment_image(image)


def test_local_a_remains_a_when_b_enrollment_is_blocked(monkeypatch, tmp_path: Path):
    user_a = UUID("aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa")
    user_b = UUID("bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb")
    image_a = tmp_path / "a.jpg"
    image_b_with_a = tmp_path / "a-and-b.jpg"
    image_a.write_bytes(b"a")
    image_b_with_a.write_bytes(b"a+b")

    class Numpy:
        @staticmethod
        def asarray(values, dtype=None): return values

    class IdentityLibrary(FakeLocalLibrary):
        api = SimpleNamespace(np=Numpy())
        current_path = ""

        def load_image_file(self, path):
            self.current_path = str(path)
            return object()

        def face_locations(self, _image, model="hog"):
            return [(0, 10, 10, 0)] * (2 if "a-and-b" in self.current_path else 1)

        def face_encodings(self, _image, known_face_locations):
            return [[0.0] * 128 for _ in known_face_locations]

        @staticmethod
        def face_distance(known, probe):
            return [sum(abs(a - b) for a, b in zip(candidate, probe)) / 128 for candidate in known]

    library = IdentityLibrary(1)
    monkeypatch.setattr(face_service.settings, "face_provider", "local")
    monkeypatch.setattr(face_service, "_load_local_library", lambda: library)
    service = FaceService()
    encoding_a = service.validate_enrollment_image(image_a)
    enrolled_a = service.enroll_face(user_a, image_a, validated_encoding=encoding_a)
    profile_b_before = json.dumps([1.0] * 128).encode()
    with pytest.raises(MultipleFacesDetectedError):
        service.validate_enrollment_image(image_b_with_a)
    profile_b_after = profile_b_before  # route never reaches the profile mutation step
    result = service.verify_face(image_a, [
        (user_b, profile_b_after, None), (user_a, enrolled_a.template_bytes, None),
    ])
    assert profile_b_after == profile_b_before
    assert result.result == "SUCCESS"
    assert result.user_id == user_a
    assert result.user_id != user_b


def test_real_local_provider_identity_e2e_when_consent_fixtures_are_supplied():
    """Opt-in only: never bundles, logs, or invents biometric fixtures."""
    paths = {name: os.getenv(name) for name in ("FACE_TEST_A_IMAGE", "FACE_TEST_A_AND_B_IMAGE")}
    if face_service.settings.face_provider != "local" or not all(paths.values()):
        pytest.skip("Requires FACE_PROVIDER=local and explicit consented face fixture paths")
    image_a = Path(paths["FACE_TEST_A_IMAGE"])
    image_a_and_b = Path(paths["FACE_TEST_A_AND_B_IMAGE"])
    service = FaceService()
    user_a = UUID("aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa")
    encoding_a = service.validate_enrollment_image(image_a)
    profile_a = service.enroll_face(user_a, image_a, validated_encoding=encoding_a)
    with pytest.raises(MultipleFacesDetectedError):
        service.validate_enrollment_image(image_a_and_b)
    verified = service.verify_face(image_a, [(user_a, profile_a.template_bytes, None)])
    assert verified.result == "SUCCESS"
    assert verified.user_id == user_a


class NoWriteDB:
    def __init__(self):
        self.accesses = 0
        self.writes = 0

    def get(self, *_args):
        self.accesses += 1
        return None

    def scalar(self, *_args):
        self.accesses += 1
        return None

    def add(self, *_args):
        self.writes += 1

    def flush(self):
        self.writes += 1

    def commit(self):
        self.writes += 1

    def rollback(self):
        pass


def test_multiple_faces_fail_before_user_or_profile_access(monkeypatch, tmp_path: Path):
    from app.api.v1.routes import face
    database = NoWriteDB()
    monkeypatch.setattr(face.settings, "media_storage_dir", tmp_path)
    monkeypatch.setattr(
        face.FaceService, "validate_enrollment_image",
        lambda _self, _path: (_ for _ in ()).throw(MultipleFacesDetectedError(2)),
    )
    app.dependency_overrides[get_db] = lambda: database
    try:
        response = TestClient(app).post("/api/v1/face/enroll", data={"full_name": "Người B"},
            files={"image_file": ("two.jpg", b"\xff\xd8\xffsafe-test", "image/jpeg")})
        assert response.status_code == 422
        assert response.json()["error"] == {"code": "MULTIPLE_FACES_DETECTED", "details": {"face_count": 2}}
        assert database.accesses == 0
        assert database.writes == 0
        assert not list(tmp_path.rglob("*.jpg"))
    finally:
        app.dependency_overrides.clear()


def test_zero_faces_fail_before_user_or_profile_access(monkeypatch, tmp_path: Path):
    from app.api.v1.routes import face
    database = NoWriteDB()
    monkeypatch.setattr(face.settings, "media_storage_dir", tmp_path)
    monkeypatch.setattr(
        face.FaceService, "validate_enrollment_image",
        lambda _self, _path: (_ for _ in ()).throw(NoFaceDetectedError("Không phát hiện khuôn mặt.")),
    )
    app.dependency_overrides[get_db] = lambda: database
    try:
        response = TestClient(app).post("/api/v1/face/enroll", data={"full_name": "Người B"},
            files={"image_file": ("none.jpg", b"\xff\xd8\xffsafe-test", "image/jpeg")})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "NO_FACE_DETECTED"
        assert database.accesses == database.writes == 0
    finally:
        app.dependency_overrides.clear()


def test_single_face_endpoint_creates_one_user_and_one_profile(monkeypatch, tmp_path: Path):
    from app.api.v1.routes import face
    from app.models.schema import FaceProfile, User

    class DB:
        def __init__(self): self.added = []
        def get(self, *_args): return None
        def scalar(self, _query): return None
        def add(self, value):
            if getattr(value, "id", None) is None: value.id = uuid4()
            self.added.append(value)
        def flush(self): pass
        def commit(self): pass
        def rollback(self): pass
        def refresh(self, _value): pass

    database = DB()
    monkeypatch.setattr(face.settings, "face_provider", "local")
    monkeypatch.setattr(face.settings, "media_storage_dir", tmp_path)
    monkeypatch.setattr(face.FaceService, "validate_enrollment_image", lambda _self, _path: [0.1] * 128)
    monkeypatch.setattr(face, "record_event", lambda *_args, **_kwargs: None)
    app.dependency_overrides[get_db] = lambda: database
    try:
        response = TestClient(app).post("/api/v1/face/enroll", data={"full_name": "Người A"},
            files={"image_file": ("one.jpg", b"\xff\xd8\xffsafe-test", "image/jpeg")})
        assert response.status_code == 200
        assert len([value for value in database.added if isinstance(value, User)]) == 1
        assert len([value for value in database.added if isinstance(value, FaceProfile)]) == 1
    finally:
        app.dependency_overrides.clear()


def test_profile_update_does_not_touch_face_profile(monkeypatch):
    user_id = UUID("11111111-1111-1111-1111-111111111111")
    user = SimpleNamespace(id=user_id, student_code="A001", full_name="Người A", email=None,
        phone=None, faculty=None, major=None, admission_year=2024, deleted_at=None)
    biometric = object()

    class DB:
        def get(self, model, identifier):
            from app.models.schema import User
            return user if model is User and identifier == user_id else biometric
        def scalar(self, _query): return None
        def commit(self): pass
        def refresh(self, _value): pass

    app.dependency_overrides[get_db] = lambda: DB()
    try:
        response = TestClient(app).patch(f"/api/v1/users/{user_id}", json={
            "full_name": "Người A đã sửa", "major": "Công nghệ thông tin", "admission_year": 2023,
        })
        assert response.status_code == 200
        assert response.json()["data"]["full_name"] == "Người A đã sửa"
        assert biometric is not None
    finally:
        app.dependency_overrides.clear()
