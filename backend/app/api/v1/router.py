from fastapi import APIRouter
from app.api.v1.routes import runtime

from app.api.v1.routes import (
    admin,
    ai,
    book_suggestions,
    conversations,
    face,
    face_authentication,
    health,
    interactions,
    knowledge,
    kiosk,
    prompts,
    reports,
    sessions,
    surveys,
    users,
    voice,
)

api_router = APIRouter()
api_router.include_router(runtime.router, prefix="/kiosk", tags=["kiosk-stream"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(kiosk.router, prefix="/kiosk", tags=["kiosk"])
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(interactions.router, prefix="/interactions", tags=["interactions"])
api_router.include_router(face.router, prefix="/face", tags=["face-runtime"])
api_router.include_router(face_authentication.router, prefix="/face", tags=["face-mock"])
api_router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["knowledge"])
api_router.include_router(conversations.router, prefix="/conversations", tags=["conversations"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
api_router.include_router(prompts.router, prefix="/prompts", tags=["prompts"])
api_router.include_router(book_suggestions.router, tags=["book-suggestions"])
api_router.include_router(surveys.router, prefix="/surveys", tags=["surveys"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(voice.router, prefix="/voice", tags=["voice"])
