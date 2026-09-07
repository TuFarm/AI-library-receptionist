from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.errors import AppError
from app.models.schema import FaceProfile, User
from app.api.v1.routes.face import _user_data
from app.core.responses import success_response
from app.schemas.user import MockCurrentUserResponse, UserProfileRead, UserProfileUpdate
from app.services.user_service import calculate_student_year

router = APIRouter()

@router.get("/me/mock", response_model=MockCurrentUserResponse)
async def mock_current_user() -> dict:
    admission_year = 2024
    user = UserProfileRead(id=UUID("d8f8b7db-56b5-4be5-a136-19eb154ae21f"), student_code="ITCSIU24092",
        full_name="Phạm Hoàng Tuấn Tú", email="tu.pham@example.edu.vn", phone="0901234567", user_type="student",
        faculty="Công nghệ thông tin", major="Khoa học máy tính", admission_year=admission_year,
        calculated_student_year=calculate_student_year(admission_year), account_status="active", preferred_language="vi")
    return success_response(user.model_dump(mode="json"))


@router.patch("/{user_id}")
async def update_user(user_id: UUID, payload: UserProfileUpdate, db: Session = Depends(get_db)) -> dict:
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise AppError(404, "USER_NOT_FOUND", "Không tìm thấy người dùng.")
    values = payload.model_dump(exclude_unset=True)
    for field in ("student_code", "email"):
        value = values.get(field)
        if value and db.scalar(select(User).where(
            getattr(User, field) == value, User.id != user_id, User.deleted_at.is_(None)
        )):
            raise AppError(409, f"{field.upper()}_ALREADY_EXISTS", f"{field} đã được sử dụng.")
    for field, value in values.items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return success_response(_user_data(user), "Cập nhật thông tin thành công.")


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
