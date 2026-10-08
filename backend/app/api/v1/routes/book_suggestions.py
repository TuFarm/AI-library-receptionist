from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.responses import success_response
from app.core.database import get_db
from app.models.schema import BookCategory, SuggestedBook

router = APIRouter()
@router.get("/book-categories")
def database_categories(db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(BookCategory).where(BookCategory.deleted_at.is_(None)).order_by(BookCategory.category_name)).all()
    return success_response([{"id": str(row.id), "category_name": row.category_name, "description": row.description} for row in rows],
        "OK" if rows else "Chưa có thể loại sách trong cơ sở dữ liệu.")


@router.get("/suggested-books")
def database_books(category_id: UUID | None = Query(default=None), db: Session = Depends(get_db)) -> dict:
    query = select(SuggestedBook).where(SuggestedBook.deleted_at.is_(None))
    if category_id: query = query.where(SuggestedBook.category_id == category_id)
    rows = db.scalars(query.order_by(SuggestedBook.title)).all()
    return success_response([{"id": str(row.id), "category_id": str(row.category_id) if row.category_id else None,
        "external_book_id": row.external_book_id, "title": row.title, "author_name": row.author_name,
        "short_description": row.short_description} for row in rows], "OK" if rows else "Chưa có sách gợi ý.")
