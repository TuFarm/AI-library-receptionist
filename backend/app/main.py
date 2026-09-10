from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import register_error_handlers
from app.core.responses import success_response
from app.services.face_service import get_face_provider


def create_app() -> FastAPI:
    # Opt-in native providers fail during startup rather than after a visitor
    # has entered the kiosk flow. Mock and legacy local remain lazily loaded.
    if settings.face_provider == "local_opencv":
        get_face_provider("local_opencv")
    app = FastAPI(title=settings.app_name, version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            origin.strip()
            for origin in settings.kiosk_stream_origins.split(",")
            if origin.strip()
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/health", tags=["health"])
    async def health_check() -> dict:
        return success_response({"status": "ok", "app": settings.app_name})

    return app


app = create_app()
