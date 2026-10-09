from uuid import UUID
from datetime import UTC, datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from app.api.deps import require_staff
from app.core.database import get_db
from app.core.errors import AppError
from app.models.schema import User
from app.core.responses import success_response
from app.schemas.user import UserCreate, UserProfileUpdate
from app.services.user_service import (
    apply_profile_update, calculate_student_year, commit_profile,
)

router = APIRouter()


def _admin_user_data(user: User) -> dict:
    return {
        "id": str(user.id),
        "student_code": user.student_code,
        "full_name": user.full_name,
        "email": user.email,
        "faculty": user.faculty,
        "major": user.major,
        "admission_year": user.admission_year,
        "student_year": calculate_student_year(user.admission_year),
        "user_type": user.user_type,
        "account_status": user.account_status,
    }


@router.get("", dependencies=[Depends(require_staff)])
def list_users(
    search: str | None = Query(default=None, max_length=100),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    filters = [User.deleted_at.is_(None)]
    if search:
        term = search.strip().replace("/", "//").replace("%", "/%").replace("_", "/_")
        filters.append(or_(*(column.ilike(f"%{term}%", escape="/")
                            for column in (User.full_name, User.student_code, User.email))))
    total = db.scalar(select(func.count(User.id)).where(*filters)) or 0
    users = db.scalars(
        select(User).where(*filters).order_by(User.created_at.desc(), User.id).offset(offset).limit(limit)
    ).all()
    return success_response({"items": [_admin_user_data(user) for user in users], "total": total, "offset": offset, "limit": limit})


@router.post("", status_code=201, dependencies=[Depends(require_staff)])
def create_user(payload: UserCreate, db: Session = Depends(get_db)) -> dict:
    for field in ("student_code", "email"):
        value = getattr(payload, field)
        if db.scalar(select(User).where(getattr(User, field) == value)):
            raise AppError(409, f"{field.upper()}_ALREADY_EXISTS", f"{field} đã được sử dụng.")
    user = User(
        **payload.model_dump(),
        user_type="student",
        account_status="active",
        preferred_language="vi",
    )
    db.add(user)
    commit_profile(db)
    db.refresh(user)
    return success_response(_admin_user_data(user), "Tạo hồ sơ người dùng thành công.")

@router.get("/{user_id}", dependencies=[Depends(require_staff)])
def get_user(user_id: UUID, db: Session = Depends(get_db)) -> dict:
    """Get a single user profile by ID (non-biometric data only)."""
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise AppError(404, "USER_NOT_FOUND", "Không tìm thấy người dùng.")
    return success_response(_admin_user_data(user))


@router.delete("/{user_id}", dependencies=[Depends(require_staff)])
def delete_user(user_id: UUID, db: Session = Depends(get_db)) -> dict:
    """Soft-delete a user by setting deleted_at and deactivating account."""
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise AppError(404, "USER_NOT_FOUND", "Không tìm thấy người dùng.")
    user.deleted_at = datetime.now(UTC)
    user.account_status = "deactivated"
    db.commit()
    return success_response(
        {"user_id": str(user_id), "account_status": "deactivated"},
        "Đã xóa hồ sơ người dùng."
    )


@router.patch("/{user_id}", dependencies=[Depends(require_staff)])
def update_user(user_id: UUID, payload: UserProfileUpdate, db: Session = Depends(get_db)) -> dict:
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise AppError(404, "USER_NOT_FOUND", "Không tìm thấy người dùng.")
    apply_profile_update(db, user, payload.model_dump(exclude_unset=True))
    return success_response(_admin_user_data(user), "Cập nhật thông tin thành công.")
