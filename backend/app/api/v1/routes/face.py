from datetime import UTC, datetime
from decimal import Decimal
from time import perf_counter
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import owned_session, require_kiosk_device
from app.core.config import settings
from app.core.database import get_db
from app.core.errors import AppError
from app.core.responses import success_response
from app.models.schema import Device, FaceAuthenticationLog, FaceProfile, User
from app.services.face_service import (
    FaceImageError, FaceProviderUnavailable, FaceService, get_face_provider,
    MultipleFacesDetectedError, NoFaceDetectedError,
)
from app.services.interaction_service import record_event
from app.services.media_storage_service import MediaStorageService, MediaValidationError
from app.services.user_service import calculate_student_year

router = APIRouter()


def _user_data(user: User) -> dict:
    return {"id": str(user.id), "student_code": user.student_code, "full_name": user.full_name,
        "email": user.email, "phone": user.phone, "faculty": user.faculty, "major": user.major,
        "admission_year": user.admission_year, "student_year": calculate_student_year(user.admission_year)}


@router.post("/enroll")
async def enroll(
    image_file: UploadFile = File(),
    user_id: UUID | None = Form(default=None),
    full_name: str | None = Form(default=None),
    student_code: str | None = Form(default=None),
    email: str | None = Form(default=None),
    phone: str | None = Form(default=None),
    faculty: str | None = Form(default=None),
    major: str | None = Form(default=None),
    admission_year: int | None = Form(default=None),
    session_id: UUID | None = Form(default=None),
    device: Device = Depends(require_kiosk_device),
    db: Session = Depends(get_db),
) -> dict:
    storage = MediaStorageService()
    try:
        path = await storage.save_image(image_file, "enrollments")
        face_service = FaceService()
        # Detection, quality, embedding and serialization must all complete before DB access.
        enrollment_result = face_service.prepare_enrollment(path)
    except MediaValidationError as exc:
        raise AppError(400, "INVALID_IMAGE", str(exc)) from exc
    except MultipleFacesDetectedError as exc:
        storage.cleanup(path)
        raise AppError(422, "MULTIPLE_FACES_DETECTED", str(exc), {"face_count": exc.face_count}) from exc
    except NoFaceDetectedError as exc:
        storage.cleanup(path)
        raise AppError(422, "NO_FACE_DETECTED", str(exc)) from exc
    except FaceImageError as exc:
        storage.cleanup(path)
        raise AppError(422, "FACE_IMAGE_INVALID", str(exc)) from exc
    except FaceProviderUnavailable as exc:
        storage.cleanup(path)
        raise AppError(503, "FACE_PROVIDER_UNAVAILABLE", str(exc)) from exc
    except Exception:
        if "path" in locals():
            storage.cleanup(path)
        raise

    try:
        session = owned_session(db, session_id, device, required=False, active=True)
        user = None
        if user_id:
            # Re-enrollment may only replace the template of the visitor this kiosk
            # session has already identified; never an arbitrary account.
            if session is None or not session.identified or session.user_id != user_id:
                raise AppError(403, "SESSION_NOT_IDENTIFIED",
                               "Chỉ có thể đăng ký lại Face ID cho người dùng đã được xác nhận trong phiên này.")
            user = db.get(User, user_id)
            if user is None or user.deleted_at is not None:
                raise AppError(404, "USER_NOT_FOUND", "Không tìm thấy người dùng.")
        claimed = None
        if user is None and student_code:
            claimed = db.scalar(select(User).where(User.student_code == student_code, User.deleted_at.is_(None)))
        if user is None and claimed is None and email:
            claimed = db.scalar(select(User).where(User.email == email, User.deleted_at.is_(None)))
        if claimed is not None:
            # Typing someone's student code or email must not bind a new face to an
            # account that already has one. The owner re-enrolls after being recognized.
            if db.scalar(select(FaceProfile.id).where(
                FaceProfile.user_id == claimed.id, FaceProfile.active.is_(True), FaceProfile.deleted_at.is_(None),
            )):
                raise AppError(409, "FACE_ALREADY_REGISTERED",
                               "Mã sinh viên hoặc email này đã có Face ID. Vui lòng liên hệ quầy thủ thư.")
            user = claimed
        if user is None:
            if not full_name or not full_name.strip():
                raise AppError(422, "FULL_NAME_REQUIRED", "Vui lòng nhập họ và tên để đăng ký khuôn mặt.")
            user = User(full_name=full_name.strip(), student_code=student_code or None, email=email or None,
                phone=phone or None, faculty=faculty or None, major=major or None, admission_year=admission_year,
                user_type="STUDENT", account_status="ACTIVE", preferred_language="vi")
            db.add(user)
            db.flush()
        elif user is claimed:
            # A claimed profile (pre-registered by staff) keeps its existing values.
            for field, value in (("full_name", full_name.strip() if full_name else None), ("student_code", student_code),
                                 ("email", email), ("phone", phone), ("faculty", faculty), ("major", major),
                                 ("admission_year", admission_year)):
                if value not in (None, "") and getattr(user, field) in (None, ""):
                    setattr(user, field, value)
        else:
            if full_name: user.full_name = full_name.strip()
            if student_code: user.student_code = student_code
            if email: user.email = email
            if phone: user.phone = phone
            if faculty: user.faculty = faculty
            if major: user.major = major
            if admission_year is not None: user.admission_year = admission_year

        result = enrollment_result
        # Keep rollback profiles from other providers intact. A successful
        # re-enrollment updates only the same model/version profile.
        profile = db.scalar(select(FaceProfile).where(
            FaceProfile.user_id == user.id,
            FaceProfile.active.is_(True),
            FaceProfile.deleted_at.is_(None),
            FaceProfile.model_name == result.model_name,
            FaceProfile.model_version == result.model_version,
        ))
        if profile is None:
            profile = FaceProfile(user_id=user.id, enrolled_at=datetime.now(UTC), active=True)
            db.add(profile)
        profile.face_template_ref = result.template_ref
        profile.face_template_encrypted = result.template_bytes
        profile.model_name = result.model_name
        profile.model_version = result.model_version
        profile.quality_score = Decimal(str(result.quality_score))
        if session:
            session.user_id = user.id
            session.identified = True
        record_event(db, event_type="FACE_ENROLLED", session_id=session_id, user_id=user.id,
            device_id=device.id, success=True)
        db.commit()
        db.refresh(profile)
        return success_response({"face_profile_id": str(profile.id), "user_id": str(user.id),
            "user": _user_data(user), "provider": settings.face_provider, "quality_score": result.quality_score,
            "next_state": "WELCOME"}, "Đăng ký khuôn mặt thành công.")
    except MediaValidationError as exc:
        db.rollback()
        raise AppError(400, "INVALID_IMAGE", str(exc)) from exc
    except MultipleFacesDetectedError as exc:
        db.rollback()
        raise AppError(422, "MULTIPLE_FACES_DETECTED", str(exc), {"face_count": exc.face_count}) from exc
    except NoFaceDetectedError as exc:
        db.rollback()
        raise AppError(422, "NO_FACE_DETECTED", str(exc)) from exc
    except FaceImageError as exc:
        db.rollback()
        raise AppError(422, "FACE_IMAGE_INVALID", str(exc)) from exc
    except FaceProviderUnavailable as exc:
        db.rollback()
        raise AppError(503, "FACE_PROVIDER_UNAVAILABLE", str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    finally:
        if "path" in locals():
            storage.cleanup(path)


@router.post("/verify")
async def verify(session_id: UUID | None = Form(default=None), image_file: UploadFile = File(),
                 device: Device = Depends(require_kiosk_device), db: Session = Depends(get_db)) -> dict:
    storage = MediaStorageService()
    started = perf_counter()
    session = owned_session(db, session_id, device, required=False, active=True)
    try:
        path = await storage.save_image(image_file, "verification")
        provider = get_face_provider()
        profiles = db.scalars(select(FaceProfile).where(
            FaceProfile.active.is_(True),
            FaceProfile.deleted_at.is_(None),
            FaceProfile.model_name == provider.name,
            FaceProfile.model_version == provider.model_version,
        ).order_by(FaceProfile.enrolled_at)).all()
        candidates = [(
            profile.user_id,
            profile.face_template_encrypted,
            profile.face_template_ref,
            profile.model_name,
            profile.model_version,
        ) for profile in profiles]
        result = FaceService().verify_face(path, candidates)
        user = db.get(User, result.user_id) if result.user_id else None
        processing_ms = int((perf_counter() - started) * 1000)
        attempt = 1
        if session_id:
            attempt = int(db.scalar(select(func.count(FaceAuthenticationLog.id)).where(
                FaceAuthenticationLog.session_id == session_id)) or 0) + 1
        log = FaceAuthenticationLog(user_id=result.user_id, session_id=session_id,
            device_id=device.id, result=result.result,
            confidence_score=Decimal(str(result.confidence_score)) if result.confidence_score is not None else None,
            processing_time_ms=processing_ms, attempt_number=attempt,
            failure_reason=None if user else result.result, occurred_at=datetime.now(UTC))
        db.add(log)
        if user and session:
            session.user_id = user.id
            session.identified = True
        record_event(db, event_type="FACE_RECOGNIZED" if user else "FACE_FAILED", session_id=session_id,
            user_id=user.id if user else None, device_id=log.device_id, success=user is not None)
        db.commit()
        next_state = "WELCOME" if user else "FACE_UNKNOWN"
        message = f"Xin chào, {user.full_name}!" if user else "Bạn chưa có dữ liệu khuôn mặt."
        return success_response({"result": result.result, "user": _user_data(user) if user else None,
            "confidence_score": result.confidence_score, "next_state": next_state,
            "processing_time_ms": processing_ms}, message)
    except MediaValidationError as exc:
        raise AppError(400, "INVALID_IMAGE", str(exc)) from exc
    except MultipleFacesDetectedError as exc:
        raise AppError(422, "MULTIPLE_FACES_DETECTED", str(exc), {"face_count": exc.face_count}) from exc
    except NoFaceDetectedError as exc:
        raise AppError(422, "NO_FACE_DETECTED", str(exc)) from exc
    except FaceImageError as exc:
        raise AppError(422, "FACE_IMAGE_INVALID", str(exc)) from exc
    except FaceProviderUnavailable as exc:
        raise AppError(503, "FACE_PROVIDER_UNAVAILABLE", str(exc)) from exc
    finally:
        if "path" in locals():
            storage.cleanup(path)
