from pathlib import Path
from uuid import UUID
import builtins

from app.services.ai_service import AIService
from app.services.face_service import FaceProviderUnavailable, FaceService
from app.services.user_service import calculate_student_year
from fastapi.testclient import TestClient
from types import SimpleNamespace
from app.main import app
from app.core.database import get_db


def test_face_mock_is_deterministic_and_supports_unknown(monkeypatch, tmp_path: Path):
    from app.services import face_service
    monkeypatch.setattr(face_service.settings, "face_provider", "mock")
    user_id = UUID("11111111-1111-1111-1111-111111111111")
    image = tmp_path / "known.jpg"; image.write_bytes(b"test-image")
    first = FaceService().enroll_face(user_id, image)
    second = FaceService().enroll_face(user_id, image)
    assert first.template_ref == second.template_ref
    assert FaceService().verify_face(image, user_id).result == "SUCCESS"
    unknown = tmp_path / "unknown-face.jpg"; unknown.write_bytes(b"test-image-2")
    result = FaceService().verify_face(unknown, user_id)
    assert result.result == "UNKNOWN_FACE" and result.user_id is None


def test_contextual_mock_ai_and_student_year():
    assert "WiFi" in AIService().answer("Wifi thư viện là gì?").text
    assert calculate_student_year(2024, 2026) == 3


def test_local_face_provider_unavailable_is_clear(monkeypatch, tmp_path: Path):
    from app.services import face_service
    image = tmp_path / "face.jpg"; image.write_bytes(b"image")
    monkeypatch.setattr(face_service.settings, "face_provider", "local")
    monkeypatch.setattr(face_service, "_load_local_library", lambda: (_ for _ in ()).throw(
        FaceProviderUnavailable("Local FaceID provider is not installed. Switch FACE_PROVIDER=mock.")))
    try:
        FaceService().enroll_face(UUID("11111111-1111-1111-1111-111111111111"), image)
        raise AssertionError("Expected optional provider error")
    except FaceProviderUnavailable as exc:
        assert "FACE_PROVIDER=mock" in str(exc)


def test_local_face_library_converts_dependency_system_exit(monkeypatch):
    from app.services import face_service
    real_import = builtins.__import__

    def import_with_broken_models(name, *args, **kwargs):
        if name == "face_recognition":
            raise SystemExit("face_recognition_models could not load")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_with_broken_models)
    try:
        face_service._load_local_library()
        raise AssertionError("Expected optional provider error")
    except FaceProviderUnavailable as exc:
        assert "setuptools<82" in str(exc)


def test_mock_face_unknown_without_profiles(monkeypatch, tmp_path: Path):
    from app.services import face_service
    monkeypatch.setattr(face_service.settings, "face_provider", "mock")
    image = tmp_path / "face.jpg"; image.write_bytes(b"image")
    result = FaceService().verify_face(image, [])
    assert result.result == "UNKNOWN_FACE"
    assert result.user_id is None


def test_local_match_uses_distance_threshold_and_reports_embedding_metrics(monkeypatch):
    from app.services import face_service
    user_id = UUID("11111111-1111-1111-1111-111111111111")

    class FakeArray(list):
        def __sub__(self, other):
            return FakeArray(a - b for a, b in zip(self, other))

    class FakeNumpy:
        @staticmethod
        def asarray(values, dtype=None):
            return FakeArray(FakeArray(row) if isinstance(row, list) else row for row in values)

    class FakeLibrary:
        api = SimpleNamespace(np=FakeNumpy())

        @staticmethod
        def face_distance(known, probe):
            assert isinstance(known, FakeArray)
            assert isinstance(probe, FakeArray)
            return [0.55]

    monkeypatch.setattr(face_service, "_load_local_library", lambda: FakeLibrary())
    template = __import__("json").dumps([0.1] * 128).encode()
    result = FaceService().verify_encoding([0.1] * 128, [(user_id, template, None)])
    assert result.result == "SUCCESS"
    assert result.user_id == user_id
    assert result.distance == 0.55
    assert result.confidence_score == 0.7708
    assert result.embedding_dimension == 128


def test_local_match_rejects_distance_above_operational_threshold(monkeypatch):
    from app.services import face_service

    class FakeNumpy:
        @staticmethod
        def asarray(values, dtype=None):
            return tuple(tuple(row) if isinstance(row, list) else row for row in values)

    class FakeLibrary:
        api = SimpleNamespace(np=FakeNumpy())

        @staticmethod
        def face_distance(_known, _probe):
            return [0.68]

    monkeypatch.setattr(face_service, "_load_local_library", lambda: FakeLibrary())
    template = __import__("json").dumps([0.1] * 128).encode()
    result = FaceService().verify_encoding(
        [0.1] * 128, [(UUID("11111111-1111-1111-1111-111111111111"), template, None)]
    )
    assert result.result == "LOW_CONFIDENCE"
    assert result.user_id is None


def test_gemini_mode_without_key_falls_back(monkeypatch):
    from app.services import ai_service
    monkeypatch.setattr(ai_service.settings, "ai_provider", "gemini")
    monkeypatch.setattr(ai_service.settings, "gemini_api_key", "")
    result = AIService().answer("Xin chào")
    assert result.provider == "mock"
    assert result.used_fallback is True
    assert "GEMINI_API_KEY" in (result.warning or "")


def test_face_enroll_requires_image():
    response = TestClient(app).post("/api/v1/face/enroll", data={"full_name": "Nguyễn Văn A"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_face_verify_endpoint_reports_local_provider_unavailable(monkeypatch, tmp_path: Path):
    from app.services import face_service
    class EmptyScalars:
        def all(self): return []
    class FakeDB:
        def scalars(self, _query): return EmptyScalars()
        def scalar(self, _query): return None
        def get(self, _model, _identifier): return None
    monkeypatch.setattr(face_service.settings, "face_provider", "local")
    monkeypatch.setattr(face_service.settings, "media_storage_dir", tmp_path)
    monkeypatch.setattr(face_service, "_load_local_library", lambda: (_ for _ in ()).throw(
        FaceProviderUnavailable("Local FaceID provider is not installed. Switch FACE_PROVIDER=mock.")))
    app.dependency_overrides[get_db] = lambda: FakeDB()
    try:
        response = TestClient(app).post("/api/v1/face/verify",
            files={"image_file": ("face.jpg", b"\xff\xd8\xffdevelopment", "image/jpeg")})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "FACE_PROVIDER_UNAVAILABLE"
    finally:
        app.dependency_overrides.clear()


def test_ai_answer_endpoint_falls_back_without_gemini_key(monkeypatch):
    from app.api.v1.routes import ai
    from app.services import ai_service
    conversation_id = UUID("66666666-6666-6666-6666-666666666666")
    user_message_id = UUID("77777777-7777-7777-7777-777777777777")
    fake_conversation = SimpleNamespace(id=conversation_id, user_id=None)
    class EmptyScalars:
        def all(self): return []
    class FakeDB:
        def __init__(self): self.pending = []
        def get(self, model, identifier):
            from app.models.schema import Conversation
            return fake_conversation if model is Conversation and identifier == conversation_id else None
        def scalars(self, _query): return EmptyScalars()
        def add(self, value): self.pending.append(value)
        def flush(self):
            for value in self.pending:
                if getattr(value, "id", None) is None: value.id = UUID("88888888-8888-4888-8888-888888888888")
        def commit(self): pass
    monkeypatch.setattr(ai_service.settings, "ai_provider", "gemini")
    monkeypatch.setattr(ai_service.settings, "gemini_api_key", "")
    monkeypatch.setattr(ai, "save_message", lambda *args: SimpleNamespace(id=user_message_id))
    monkeypatch.setattr(ai, "record_event", lambda *args, **kwargs: None)
    app.dependency_overrides[get_db] = lambda: FakeDB()
    try:
        response = TestClient(app).post("/api/v1/ai/answer", json={
            "conversation_id": str(conversation_id), "message_text": "Xin chào"})
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["provider"] == "mock"
        assert data["next_state"] == "AI_VOICE_CHAT"
        assert "GEMINI_API_KEY" in data["warning"]
    finally:
        app.dependency_overrides.clear()


def test_browser_transcript_endpoint_persists_message_contract(monkeypatch):
    from app.api.v1.routes import voice
    conversation_id = UUID("33333333-3333-3333-3333-333333333333")
    message_id = UUID("44444444-4444-4444-4444-444444444444")
    fake_conversation = SimpleNamespace(id=conversation_id, session_id=UUID("55555555-5555-5555-5555-555555555555"), user_id=None)
    class FakeDB:
        def get(self, model, identifier): return fake_conversation
    app.dependency_overrides[get_db] = lambda: FakeDB()
    monkeypatch.setattr(voice, "save_message", lambda *args: SimpleNamespace(id=message_id))
    try:
        response = TestClient(app).post("/api/v1/voice/browser-transcript", json={
            "conversation_id": str(conversation_id), "transcript": "Thư viện mở cửa lúc mấy giờ?", "confidence_score": 0.91})
        assert response.status_code == 200
        assert response.json()["data"]["message_id"] == str(message_id)
    finally:
        app.dependency_overrides.clear()
