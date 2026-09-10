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
    FaceImageError, FaceProviderUnavailable, FaceService,
    MultipleFacesDetectedError, NoFaceDetectedError, ProviderFaceDetection,
    QualityGatedFace, VersionedFaceEmbedding,
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


def opencv_detection():
    row = (
        20.0, 30.0, 200.0, 220.0,
        75.0, 100.0, 165.0, 100.0, 120.0, 145.0,
        85.0, 205.0, 155.0, 205.0, 0.98,
    )
    return ProviderFaceDetection(
        (30, 220, 250, 20),
        {
            "right_eye": [(75, 100)],
            "left_eye": [(165, 100)],
            "nose_tip": [(120, 145)],
            "top_lip": [(85, 205), (155, 205)],
        },
        row,
    )


class FakeOpenCVEnrollmentProvider:
    name = "opencv-sface-128d"
    model_version = "2021dec"

    def __init__(self, detections, *, quality_error=None, embedding_error=None):
        self.detections = detections
        self.quality_error = quality_error
        self.embedding_error = embedding_error
        self.calls = []

    def decode_image(self, _path):
        self.calls.append("decode")
        return object()

    def detect_faces(self, _image):
        self.calls.append("detect")
        return list(self.detections)

    def add_quality_input(self, _image, detections):
        self.calls.append("quality_input")
        return list(detections)

    def assess_enrollment_quality(self, _image, _detection):
        self.calls.append("quality")
        if self.quality_error:
            raise self.quality_error
        return 0.91

    def create_embedding(self, _image, gated_face):
        self.calls.append("embedding")
        assert isinstance(gated_face, QualityGatedFace)
        if self.embedding_error:
            raise self.embedding_error
        return VersionedFaceEmbedding(self.name, self.model_version, 128, [1.0] + [0.0] * 127)

    def supports_profile(self, model_name, model_version):
        return model_name == self.name and model_version == self.model_version


def post_opencv_enrollment(monkeypatch, tmp_path: Path, database, provider):
    from app.api.v1.routes import face

    monkeypatch.setattr(face.settings, "face_provider", "local_opencv")
    monkeypatch.setattr(face.settings, "media_storage_dir", tmp_path)
    monkeypatch.setattr(face_service, "get_face_provider", lambda _name=None: provider)
    app.dependency_overrides[get_db] = lambda: database
    return TestClient(app).post(
        "/api/v1/face/enroll",
        data={"full_name": "Người OpenCV"},
        files={"image_file": ("face.jpg", b"\xff\xd8\xffsafe-test", "image/jpeg")},
    )


@pytest.mark.parametrize(
    "detections, expected_code",
    [([], "NO_FACE_DETECTED"), ([opencv_detection(), opencv_detection()], "MULTIPLE_FACES_DETECTED")],
)
def test_opencv_face_count_failure_has_no_database_access(
    monkeypatch, tmp_path: Path, detections, expected_code
):
    database = NoWriteDB()
    provider = FakeOpenCVEnrollmentProvider(detections)
    try:
        response = post_opencv_enrollment(monkeypatch, tmp_path, database, provider)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == expected_code
        assert database.accesses == database.writes == 0
        assert "quality" not in provider.calls
        assert "embedding" not in provider.calls
        assert not list(tmp_path.rglob("*.jpg"))
    finally:
        app.dependency_overrides.clear()


def test_opencv_quality_failure_never_creates_embedding_or_database_state(monkeypatch, tmp_path: Path):
    database = NoWriteDB()
    provider = FakeOpenCVEnrollmentProvider(
        [opencv_detection()], quality_error=FaceImageError("quality rejected")
    )
    try:
        response = post_opencv_enrollment(monkeypatch, tmp_path, database, provider)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "FACE_IMAGE_INVALID"
        assert database.accesses == database.writes == 0
        assert provider.calls[-1] == "quality"
        assert "embedding" not in provider.calls
    finally:
        app.dependency_overrides.clear()


def test_opencv_sface_failure_after_detection_leaves_no_database_state(monkeypatch, tmp_path: Path):
    database = NoWriteDB()
    provider = FakeOpenCVEnrollmentProvider(
        [opencv_detection()], embedding_error=FaceImageError("SFace failed safely")
    )
    try:
        response = post_opencv_enrollment(monkeypatch, tmp_path, database, provider)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "FACE_IMAGE_INVALID"
        assert database.accesses == database.writes == 0
        assert provider.calls == ["decode", "detect", "quality_input", "quality", "embedding"]
        assert not list(tmp_path.rglob("*.jpg"))
    finally:
        app.dependency_overrides.clear()


def test_opencv_single_quality_face_enrollment_succeeds_with_versioned_profile(
    monkeypatch, tmp_path: Path
):
    from app.api.v1.routes import face
    from app.models.schema import FaceProfile, User

    class DB:
        def __init__(self):
            self.added = []
            self.commits = 0

        def get(self, *_args):
            return None

        def scalar(self, _query):
            return None

        def add(self, value):
            if getattr(value, "id", None) is None:
                value.id = uuid4()
            self.added.append(value)

        def flush(self):
            pass

        def commit(self):
            self.commits += 1

        def rollback(self):
            pass

        def refresh(self, _value):
            pass

    database = DB()
    provider = FakeOpenCVEnrollmentProvider([opencv_detection()])
    monkeypatch.setattr(face, "record_event", lambda *_args, **_kwargs: None)
    try:
        response = post_opencv_enrollment(monkeypatch, tmp_path, database, provider)
        assert response.status_code == 200
        assert response.json()["data"]["provider"] == "local_opencv"
        assert provider.calls == ["decode", "detect", "quality_input", "quality", "embedding"]
        users = [value for value in database.added if isinstance(value, User)]
        profiles = [value for value in database.added if isinstance(value, FaceProfile)]
        assert len(users) == len(profiles) == 1
        assert profiles[0].model_name == "opencv-sface-128d"
        assert profiles[0].model_version == "2021dec"
        assert json.loads(profiles[0].face_template_encrypted) == [1.0] + [0.0] * 127
        assert database.commits == 1
        assert not list(tmp_path.rglob("*.jpg"))
    finally:
        app.dependency_overrides.clear()


def test_successful_sface_enrollment_keeps_dlib_profile_for_rollback(
    monkeypatch, tmp_path: Path
):
    from app.api.v1.routes import face
    from app.models.schema import FaceProfile, User

    user = User(
        id=uuid4(), full_name="Người đã có dlib", user_type="STUDENT",
        account_status="ACTIVE",
    )
    dlib_profile = FaceProfile(
        id=uuid4(), user_id=user.id, face_template_encrypted=b"dlib-template",
        model_name="face-recognition-hog-128d", model_version="1",
        enrolled_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        active=True,
    )

    class DB:
        def __init__(self):
            self.added = []

        def get(self, model, identifier):
            return user if model is User and identifier == user.id else None

        def scalar(self, query):
            statement = str(query)
            assert "face_profiles.model_name" in statement
            assert "face_profiles.model_version" in statement
            return None

        def add(self, value):
            if getattr(value, "id", None) is None:
                value.id = uuid4()
            self.added.append(value)

        def flush(self): pass
        def commit(self): pass
        def rollback(self): pass
        def refresh(self, _value): pass

    database = DB()
    provider = FakeOpenCVEnrollmentProvider([opencv_detection()])
    monkeypatch.setattr(face, "record_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(face.settings, "face_provider", "local_opencv")
    monkeypatch.setattr(face.settings, "media_storage_dir", tmp_path)
    monkeypatch.setattr(face_service, "get_face_provider", lambda _name=None: provider)
    app.dependency_overrides[get_db] = lambda: database
    try:
        response = TestClient(app).post(
            "/api/v1/face/enroll",
            data={"user_id": str(user.id), "full_name": user.full_name},
            files={"image_file": ("face.jpg", b"\xff\xd8\xffsafe-test", "image/jpeg")},
        )
        assert response.status_code == 200
        sface_profiles = [value for value in database.added if isinstance(value, FaceProfile)]
        assert len(sface_profiles) == 1
        assert sface_profiles[0].model_name == "opencv-sface-128d"
        assert dlib_profile.model_name == "face-recognition-hog-128d"
        assert dlib_profile.face_template_encrypted == b"dlib-template"
    finally:
        app.dependency_overrides.clear()


def test_opencv_missing_models_returns_503_before_database_access(monkeypatch, tmp_path: Path):
    from app.api.v1.routes import face

    database = NoWriteDB()
    monkeypatch.setattr(face.settings, "face_provider", "local_opencv")
    monkeypatch.setattr(face.settings, "media_storage_dir", tmp_path)
    monkeypatch.setattr(face.settings, "face_yunet_model_path", None)
    monkeypatch.setattr(face.settings, "face_sface_model_path", None)
    face_service._get_opencv_provider.cache_clear()
    app.dependency_overrides[get_db] = lambda: database
    try:
        response = TestClient(app).post(
            "/api/v1/face/enroll",
            data={"full_name": "Người OpenCV"},
            files={"image_file": ("face.jpg", b"\xff\xd8\xffsafe-test", "image/jpeg")},
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "FACE_PROVIDER_UNAVAILABLE"
        assert "model YuNet" in response.json()["message"]
        assert database.accesses == database.writes == 0
        assert not list(tmp_path.rglob("*.jpg"))
    finally:
        face_service._get_opencv_provider.cache_clear()
        app.dependency_overrides.clear()


def test_multiple_faces_fail_before_user_or_profile_access(monkeypatch, tmp_path: Path):
    from app.api.v1.routes import face
    database = NoWriteDB()
    monkeypatch.setattr(face.settings, "media_storage_dir", tmp_path)
    monkeypatch.setattr(
        face.FaceService, "prepare_enrollment",
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
        face.FaceService, "prepare_enrollment",
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
    monkeypatch.setattr(face_service, "_load_local_library", lambda: FakeLocalLibrary(1))
    monkeypatch.setattr(face, "record_event", lambda *_args, **_kwargs: None)
    app.dependency_overrides[get_db] = lambda: database
    try:
        response = TestClient(app).post("/api/v1/face/enroll", data={"full_name": "Người A"},
            files={"image_file": ("one.jpg", b"\xff\xd8\xffsafe-test", "image/jpeg")})
        assert response.status_code == 200
        assert len([value for value in database.added if isinstance(value, User)]) == 1
        profiles = [value for value in database.added if isinstance(value, FaceProfile)]
        assert len(profiles) == 1
        assert profiles[0].model_name == "face-recognition-hog-128d"
        assert profiles[0].model_version == "1"
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
