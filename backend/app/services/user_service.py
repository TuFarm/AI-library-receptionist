"""Small user-domain helpers shared by admin and kiosk routes."""
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.schema import FaceProfile, User


def calculate_student_year(
    admission_year: int | None, current_year: int | None = None
) -> int | None:
    """Return the 1-based study year, or None for missing/future admission years."""
    if admission_year is None:
        return None
    effective_year = current_year if current_year is not None else datetime.now(UTC).year
    if admission_year > effective_year:
        return None
    return effective_year - admission_year + 1


def commit_profile(db: Session) -> None:
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


def apply_profile_update(db: Session, user: User, values: dict) -> User:
    """Apply validated non-biometric profile fields; student code and email stay unique."""
    for field in ("student_code", "email"):
        value = values.get(field)
        if value and db.scalar(select(User).where(getattr(User, field) == value, User.id != user.id)):
            raise AppError(409, f"{field.upper()}_ALREADY_EXISTS", f"{field} đã được sử dụng.")
    for field, value in values.items():
        setattr(user, field, value)
    commit_profile(db)
    db.refresh(user)
    return user


def delete_face_profiles(db: Session, user_id: UUID) -> int:
    profiles = db.scalars(select(FaceProfile).where(
        FaceProfile.user_id == user_id, FaceProfile.active.is_(True), FaceProfile.deleted_at.is_(None)
    )).all()
    for profile in profiles:
        # Explicit user-confirmed hard deletion removes the biometric material.
        db.delete(profile)
    user = db.get(User, user_id)
    if user is not None:
        user.face_consent_at = user.face_consent_version = None
    db.commit()
    return len(profiles)
