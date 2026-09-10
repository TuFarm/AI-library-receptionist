from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Library Receptionist Assistant"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://ai_library:ai_library_dev@localhost:5432/ai_library"
    redis_url: str = "redis://localhost:6379/0"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    gemini_timeout_seconds: float = 20.0
    environment: str = "development"
    api_version: str = "v1"
    media_storage_dir: Path = Path(__file__).resolve().parents[2] / "storage" / "media"
    media_retain_development_files: bool = False
    face_provider: str = "mock"
    face_yunet_model_path: Path | None = None
    face_sface_model_path: Path | None = None
    face_yunet_model_sha256: str = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
    face_sface_model_sha256: str = "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"
    face_yunet_confidence_threshold: float = Field(default=0.9, gt=0, le=1)
    face_yunet_nms_threshold: float = Field(default=0.3, gt=0, le=1)
    face_sface_cosine_threshold: float | None = Field(default=None, ge=-1, le=1)
    face_analysis_width: int = Field(default=640, ge=320, le=1920)
    face_frame_interval_ms: int = Field(default=100, ge=25, le=2000)
    face_recognition_cadence_ms: int = Field(default=500, ge=100, le=5000)
    face_gallery_ttl_ms: int = Field(default=5000, ge=0, le=300000)
    face_diagnostics_enabled: bool = False
    voice_provider: str = "mock"
    ai_provider: str = "mock"
    kiosk_session_timeout_seconds: int = 60
    kiosk_stream_origins: str = "http://localhost:5173,http://127.0.0.1:5173,null"
    face_confidence_threshold: float = 0.75
    face_distance_threshold: float = 0.60
    registration_stable_frames: int = 5
    registration_stable_ms: int = 700
    max_image_upload_mb: int = 5
    max_audio_upload_mb: int = 15

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
