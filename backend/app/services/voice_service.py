import base64
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.core.config import settings

AUDIO_MIME_TYPES = {".wav": "audio/wav", ".webm": "audio/webm", ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".ogg": "audio/ogg"}
TRANSCRIBE_INSTRUCTION = ("Chép lại nguyên văn lời nói tiếng Việt trong đoạn ghi âm này. "
                          "Chỉ trả về đúng văn bản đã chép, không thêm lời giải thích, dấu ngoặc hay tiền tố. "
                          "Nếu không có lời nói rõ ràng, trả về chuỗi rỗng.")


@dataclass
class TranscriptionResult:
    transcript: str
    provider: str
    confidence_score: float | None = None
    warning: str | None = None


class VoiceService:
    def transcribe(self, path: Path) -> TranscriptionResult:
        if settings.voice_provider == "browser":
            return TranscriptionResult("", "browser", warning="Use /voice/browser-transcript with Web Speech API output.")
        if settings.voice_provider == "gemini":
            if not settings.gemini_api_key:
                return TranscriptionResult("", "gemini", warning="GEMINI_API_KEY is missing; server speech recognition is unavailable.")
            return self._gemini(path)
        # Test/development only: the kiosk never submits a mock transcript as a visitor question.
        return TranscriptionResult("Thư viện mở cửa lúc mấy giờ?", "mock")

    def _gemini(self, path: Path) -> TranscriptionResult:
        """Server-side STT for kiosks without Web Speech (e.g. Electron), using the configured Gemini model."""
        mime_type = AUDIO_MIME_TYPES.get(path.suffix.lower(), "audio/webm")
        payload = {"contents": [{"role": "user", "parts": [
            {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(path.read_bytes()).decode("ascii")}},
            {"text": TRANSCRIBE_INSTRUCTION},
        ]}], "generationConfig": {"temperature": 0}}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent"
        try:
            response = httpx.post(url, headers={"x-goog-api-key": settings.gemini_api_key, "Content-Type": "application/json"},
                                  json=payload, timeout=settings.gemini_timeout_seconds)
            response.raise_for_status()
            parts = response.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
            transcript = " ".join("".join(part.get("text", "") for part in parts).split()).strip().strip('"“”')
        except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
            return TranscriptionResult("", "gemini", warning=f"Gemini speech recognition failed ({type(exc).__name__}).")
        return TranscriptionResult(transcript, "gemini", warning=None if transcript else "No speech was recognised.")
