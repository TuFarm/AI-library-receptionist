from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_staff
from app.core.config import settings
from app.core.database import get_db
from app.core.responses import success_response
from app.models.schema import KnowledgeChunk, KnowledgeDocument
from app.schemas.knowledge import KnowledgeDocumentUpdate, KnowledgeSearch, KnowledgeTextCreate
from app.services import knowledge_service
from app.services.rag_service import retrieve

router = APIRouter()
# Knowledge is library content, so both librarians and admins manage it.
staff_router = APIRouter(dependencies=[Depends(require_staff)])


def _document_data(document: KnowledgeDocument, chunk_count: int) -> dict:
    source = document.source
    return {"id": str(document.id), "title": document.title, "source_type": source.source_type,
            "original_file_name": source.original_file_name, "file_size": source.file_size,
            "status": document.processing_status, "processing_error": source.processing_error,
            "is_active": document.is_active, "chunk_count": chunk_count,
            "created_at": document.created_at.isoformat() if document.created_at else None,
            "updated_at": document.updated_at.isoformat() if document.updated_at else None}


def _single(db: Session, document: KnowledgeDocument) -> dict:
    return _document_data(document, knowledge_service.chunk_counts(db, [document.id]).get(document.id, 0))


def _saved_message(document: KnowledgeDocument, success: str) -> str:
    return success if document.processing_status == "processed" else "Đã lưu tài liệu nhưng không xử lý được nội dung."


@staff_router.get("/documents")
def list_documents(search: str = Query(default="", max_length=200), status: str | None = Query(default=None, pattern="^(processing|processed|failed)$"),
                   offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100),
                   db: Session = Depends(get_db)) -> dict:
    documents, total = knowledge_service.list_documents(db, search=search, status=status, offset=offset, limit=limit)
    counts = knowledge_service.chunk_counts(db, [document.id for document in documents])
    return success_response({"items": [_document_data(document, counts.get(document.id, 0)) for document in documents],
                             "total": total, "max_upload_mb": settings.max_knowledge_upload_mb})


@staff_router.post("/documents", status_code=201)
def upload_document(file: UploadFile = File(), title: str | None = Form(default=None, max_length=500),
                    db: Session = Depends(get_db)) -> dict:
    # Sync on purpose: PDF/Word/Excel parsing runs in the threadpool, not on the kiosk WebSocket's event loop.
    data = file.file.read(settings.max_knowledge_upload_mb * 1024 * 1024 + 1)
    document = knowledge_service.create_from_upload(db, file_name=file.filename or "", data=data,
                                                     mime_type=file.content_type, title=title)
    return success_response(_single(db, document), _saved_message(document, "Đã tải lên và xử lý tài liệu."))


@staff_router.post("/documents/text", status_code=201)
def create_text_document(payload: KnowledgeTextCreate, db: Session = Depends(get_db)) -> dict:
    document = knowledge_service.create_from_text(db, title=payload.title, content=payload.content)
    return success_response(_single(db, document), _saved_message(document, "Đã thêm tài liệu văn bản."))


@staff_router.get("/documents/{document_id}")
def get_document(document_id: UUID, db: Session = Depends(get_db)) -> dict:
    document = knowledge_service.get_document(db, document_id)
    chunks = db.scalars(select(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id)
                        .order_by(KnowledgeChunk.chunk_index).limit(200)).all()
    return success_response({**_single(db, document), "chunks": [
        {"id": str(chunk.id), "index": chunk.chunk_index, "text": chunk.chunk_text,
         "page_number": chunk.page_number, "sheet_name": chunk.sheet_name} for chunk in chunks]})


@staff_router.patch("/documents/{document_id}")
def update_document(document_id: UUID, payload: KnowledgeDocumentUpdate, db: Session = Depends(get_db)) -> dict:
    document = knowledge_service.update(db, document_id, title=payload.title, is_active=payload.is_active)
    return success_response(_single(db, document), "Đã cập nhật tài liệu.")


@staff_router.post("/documents/{document_id}/reprocess")
def reprocess_document(document_id: UUID, db: Session = Depends(get_db)) -> dict:
    document = knowledge_service.reprocess(db, document_id)
    return success_response(_single(db, document), _saved_message(document, "Đã xử lý lại tài liệu."))


@staff_router.delete("/documents/{document_id}")
def delete_document(document_id: UUID, db: Session = Depends(get_db)) -> dict:
    knowledge_service.remove(db, document_id)
    return success_response({"id": str(document_id)}, "Đã xóa tài liệu khỏi kho tri thức.")


@staff_router.post("/search")
def search(payload: KnowledgeSearch, db: Session = Depends(get_db)) -> dict:
    """Lets staff check which chunks a question would retrieve, exactly as the kiosk AI does."""
    chunks = retrieve(db, payload.query, payload.top_k)
    data = [{**chunk.citation(index), "text": chunk.text, "score": chunk.score}
            for index, chunk in enumerate(chunks, start=1)]
    return success_response(data, "Đã tìm thấy đoạn tri thức phù hợp." if data else "Không có đoạn tri thức phù hợp.")
