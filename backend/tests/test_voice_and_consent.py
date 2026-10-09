"""Server-side speech recognition (fallback when Web Speech is unavailable) and Face ID consent lifecycle."""
import base64
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.models.schema import FaceProfile, User
from app.services import voice_service
from app.services.user_service import delete_face_profiles
from app.services.voice_service import VoiceService

WEBM = b"\x1aE\xdf\xa3" + b"\x00" * 64


class FakeGemini:
    def __init__(self, text=None, error=None): self.text, self.error, self.payload = text, error, None

    def __call__(self, url, headers, json, timeout):
        self.payload = json
        if self.error:
            raise self.error
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": self.text}]}}]},
                              request=httpx.Request("POST", url))


@pytest.fixture
def gemini(monkeypatch):
    monkeypatch.setattr(settings, "voice_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "test")


def test_gemini_transcribes_inline_audio_with_configured_model(gemini, monkeypatch, tmp_path):
    audio = tmp_path / "turn.webm"; audio.write_bytes(WEBM)
    fake = FakeGemini('  "Thư viện   mở cửa lúc mấy giờ?"\n')
    monkeypatch.setattr(voice_service.httpx, "post", fake)
    result = VoiceService().transcribe(audio)
    assert (result.transcript, result.provider, result.warning) == ("Thư viện mở cửa lúc mấy giờ?", "gemini", None)
    inline = fake.payload["contents"][0]["parts"][0]["inline_data"]
    assert inline["mime_type"] == "audio/webm" and base64.b64decode(inline["data"]) == WEBM


@pytest.mark.parametrize("fake", [FakeGemini(error=httpx.ConnectError("offline")), FakeGemini("   ")])
def test_gemini_failure_or_silence_returns_no_transcript(gemini, monkeypatch, tmp_path, fake):
    audio = tmp_path / "turn.webm"; audio.write_bytes(WEBM)
    monkeypatch.setattr(voice_service.httpx, "post", fake)
    result = VoiceService().transcribe(audio)
    assert result.transcript == "" and result.provider == "gemini" and result.warning


def test_missing_key_never_invents_a_transcript(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "voice_provider", "gemini"); monkeypatch.setattr(settings, "gemini_api_key", "")
    result = VoiceService().transcribe(tmp_path / "unused.webm")
    assert result.transcript == "" and "GEMINI_API_KEY" in result.warning


def test_transcribe_endpoint_accepts_kiosk_recordings_without_storing_them(gemini, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "media_storage_dir", tmp_path)
    monkeypatch.setattr(settings, "media_retain_development_files", False)
    monkeypatch.setattr(voice_service.httpx, "post", FakeGemini("Phòng học nhóm ở đâu?"))
    response = TestClient(app).post("/api/v1/voice/transcribe", files={"audio_file": ("turn.webm", WEBM, "audio/webm")})
    assert response.status_code == 200, response.json()
    assert response.json()["data"]["transcript"] == "Phòng học nhóm ở đâu?"
    assert not list(tmp_path.rglob("*.webm"))
    rejected = TestClient(app).post("/api/v1/voice/transcribe", files={"audio_file": ("turn.webm", b"not audio", "audio/webm")})
    assert rejected.status_code == 400 and rejected.json()["error"]["code"] == "INVALID_AUDIO"


def test_erasing_face_id_also_clears_the_consent_record(sqlite_db):
    user = User(full_name="Người A", user_type="STUDENT", account_status="ACTIVE",
                face_consent_at=datetime.now(UTC), face_consent_version="2026-10")
    sqlite_db.add(user); sqlite_db.flush()
    sqlite_db.add(FaceProfile(user_id=user.id, enrolled_at=datetime.now(UTC), active=True,
                              model_name="m", model_version="1", face_template_ref="ref"))
    sqlite_db.commit()
    assert delete_face_profiles(sqlite_db, user.id, source="KIOSK") == 1
    sqlite_db.refresh(user)
    assert user.face_consent_at is None and user.face_consent_version is None
