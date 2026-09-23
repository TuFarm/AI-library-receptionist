from uuid import UUID
from datetime import UTC, datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.api.deps import require_admin_credentials
from app.core.database import get_db
from app.core.errors import AppError
from app.models.schema import FaceProfile, User
from app.core.responses import success_response
from app.schemas.user import MockCurrentUserResponse, UserCreate, UserProfileRead, UserProfileUpdate
from app.services.user_service import calculate_student_year

router = APIRouter()


def _admin_user_data(user: User) -> dict:
    return {
        "id": str(user.id),
        "student_code": user.student_code,
        "full_name": user.full_name,
        "email": user.email,
        "phone": user.phone,
        "faculty": user.faculty,
        "major": user.major,
        "admission_year": user.admission_year,
        "student_year": calculate_student_year(user.admission_year),
        "user_type": user.user_type,
        "account_status": user.account_status,
    }


@router.get("", dependencies=[Depends(require_admin_credentials)])
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


def _commit_profile(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # Unique constraints also cover deleted profiles and concurrent writes.
        if getattr(exc.orig, "sqlstate", None) == "23505" or getattr(
            exc.orig, "sqlite_errorname", None
        ) == "SQLITE_CONSTRAINT_UNIQUE":
            raise AppError(409, "USER_PROFILE_CONFLICT", "Mã sinh viên hoặc email đã được sử dụng.") from None
        raise


@router.post("", status_code=201, dependencies=[Depends(require_admin_credentials)])
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
    _commit_profile(db)
    db.refresh(user)
    return success_response(_admin_user_data(user), "Tạo hồ sơ người dùng thành công.")

@router.get("/me/mock", response_model=MockCurrentUserResponse)
async def mock_current_user() -> dict:
    admission_year = 2024
    user = UserProfileRead(id=UUID("d8f8b7db-56b5-4be5-a136-19eb154ae21f"), student_code="ITCSIU24092",
        full_name="Phạm Hoàng Tuấn Tú", email="tu.pham@example.edu.vn", phone="0901234567", user_type="student",
        faculty="Công nghệ thông tin", major="Khoa học máy tính", admission_year=admission_year,
        calculated_student_year=calculate_student_year(admission_year), account_status="active", preferred_language="vi")
    return success_response(user.model_dump(mode="json"))


@router.get("/{user_id}", dependencies=[Depends(require_admin_credentials)])
def get_user(user_id: UUID, db: Session = Depends(get_db)) -> dict:
    """Get a single user profile by ID (non-biometric data only)."""
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise AppError(404, "USER_NOT_FOUND", "Không tìm thấy người dùng.")
    return success_response(_admin_user_data(user))


@router.delete("/{user_id}", dependencies=[Depends(require_admin_credentials)])
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


@router.patch("/{user_id}", dependencies=[Depends(require_admin_credentials)])
def update_user(user_id: UUID, payload: UserProfileUpdate, db: Session = Depends(get_db)) -> dict:
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise AppError(404, "USER_NOT_FOUND", "Không tìm thấy người dùng.")
    values = payload.model_dump(exclude_unset=True)
    for field in ("student_code", "email"):
        value = values.get(field)
        if value and db.scalar(select(User).where(
            getattr(User, field) == value, User.id != user_id
        )):
            raise AppError(409, f"{field.upper()}_ALREADY_EXISTS", f"{field} đã được sử dụng.")
    for field, value in values.items():
        setattr(user, field, value)
    _commit_profile(db)
    db.refresh(user)
    return success_response(_admin_user_data(user), "Cập nhật thông tin thành công.")


@router.delete("/{user_id}/face-profile")
async def delete_face_profile(user_id: UUID, db: Session = Depends(get_db)) -> dict:
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise AppError(404, "USER_NOT_FOUND", "Không tìm thấy người dùng.")
    profiles = db.scalars(select(FaceProfile).where(
        FaceProfile.user_id == user_id, FaceProfile.active.is_(True), FaceProfile.deleted_at.is_(None)
    )).all()
    for profile in profiles:
        # Explicit user-confirmed hard deletion removes the biometric material.
        db.delete(profile)
    db.commit()
    return success_response({"user_id": str(user_id), "deleted_profiles": len(profiles)}, "Đã xóa Face ID.")
