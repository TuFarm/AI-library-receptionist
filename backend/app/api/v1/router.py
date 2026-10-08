from fastapi import APIRouter
from app.api.v1.routes import runtime

from app.api.v1.routes import (
    admin,
    admin_access,
    admin_conversations,
    admin_surveys,
    ai,
    book_suggestions,
    conversations,
    face,
    health,
    knowledge,
    kiosk,
    reports,
    surveys,
    users,
    voice,
    departments,
)

api_router = APIRouter()
api_router.include_router(runtime.router, prefix="/kiosk", tags=["kiosk-stream"])
api_router.include_router(admin.login_router, prefix="/admin", tags=["admin"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(admin_access.router, prefix="/admin", tags=["admin-access"])
api_router.include_router(admin_conversations.router, prefix="/admin/conversations", tags=["admin-conversations"])
api_router.include_router(admin_surveys.router, prefix="/admin/surveys", tags=["admin-surveys"])
api_router.include_router(kiosk.router, prefix="/kiosk", tags=["kiosk"])
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(face.router, prefix="/face", tags=["face-runtime"])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["knowledge"])
api_router.include_router(knowledge.staff_router, prefix="/knowledge", tags=["knowledge"])
api_router.include_router(conversations.router, prefix="/conversations", tags=["conversations"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
api_router.include_router(book_suggestions.router, tags=["book-suggestions"])
api_router.include_router(surveys.router, prefix="/surveys", tags=["surveys"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(voice.router, prefix="/voice", tags=["voice"])
api_router.include_router(departments.router, prefix="/departments", tags=["departments"])
