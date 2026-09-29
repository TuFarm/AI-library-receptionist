"""Department and major management endpoints.

Provides CRUD operations for academic department and major lookup tables.
Used by admin dashboard to manage canonical department/major data.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from app.api.deps import require_staff
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AppError
from app.core.responses import success_response
from app.models.schema import Department, Major
from app.schemas.department import (
    DepartmentCreate, DepartmentUpdate,
    MajorCreate, MajorUpdate,
)

router = APIRouter()


# --- Departments ---

@router.get("")
def list_departments(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict:
    filters = [] if include_inactive else [Department.is_active.is_(True)]
    rows = db.scalars(
        select(Department).where(*filters).order_by(Department.code)
    ).all()
    return success_response([
        {"id": str(d.id), "code": d.code, "name": d.name, "is_active": d.is_active}
        for d in rows
    ])


@router.post("", status_code=201, dependencies=[Depends(require_staff)])
def create_department(payload: DepartmentCreate, db: Session = Depends(get_db)) -> dict:
    if db.scalar(select(Department).where(Department.code == payload.code)):
        raise AppError(409, "DEPARTMENT_CODE_EXISTS", f"Mã khoa '{payload.code}' đã tồn tại.")
    dept = Department(**payload.model_dump())
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return success_response(
        {"id": str(dept.id), "code": dept.code, "name": dept.name, "is_active": dept.is_active},
        "Tạo khoa thành công."
    )


@router.patch("/{dept_id}", dependencies=[Depends(require_staff)])
def update_department(
    dept_id: UUID, payload: DepartmentUpdate, db: Session = Depends(get_db),
) -> dict:
    dept = db.get(Department, dept_id)
    if dept is None:
        raise AppError(404, "DEPARTMENT_NOT_FOUND", "Không tìm thấy khoa.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(dept, field, value)
    db.commit()
    db.refresh(dept)
    return success_response(
        {"id": str(dept.id), "code": dept.code, "name": dept.name, "is_active": dept.is_active},
        "Cập nhật khoa thành công."
    )


# --- Majors ---

@router.get("/{dept_id}/majors")
def list_majors(
    dept_id: UUID,
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict:
    dept = db.get(Department, dept_id)
    if dept is None:
        raise AppError(404, "DEPARTMENT_NOT_FOUND", "Không tìm thấy khoa.")
    filters = [Major.department_id == dept_id]
    if not include_inactive:
        filters.append(Major.is_active.is_(True))
    rows = db.scalars(select(Major).where(*filters).order_by(Major.code)).all()
    return success_response([
        {"id": str(m.id), "department_id": str(m.department_id), "code": m.code, "name": m.name, "is_active": m.is_active}
        for m in rows
    ])


@router.post("/{dept_id}/majors", status_code=201, dependencies=[Depends(require_staff)])
def create_major(
    dept_id: UUID, payload: MajorCreate, db: Session = Depends(get_db),
) -> dict:
    dept = db.get(Department, dept_id)
    if dept is None:
        raise AppError(404, "DEPARTMENT_NOT_FOUND", "Không tìm thấy khoa.")
    if str(payload.department_id) != str(dept_id):
        raise AppError(422, "DEPARTMENT_MISMATCH", "department_id trong payload không khớp URL.")
    if db.scalar(select(Major).where(Major.code == payload.code)):
        raise AppError(409, "MAJOR_CODE_EXISTS", f"Mã ngành '{payload.code}' đã tồn tại.")
    major = Major(**payload.model_dump())
    db.add(major)
    db.commit()
    db.refresh(major)
    return success_response(
        {"id": str(major.id), "department_id": str(major.department_id), "code": major.code, "name": major.name, "is_active": major.is_active},
        "Tạo ngành thành công."
    )


@router.patch("/majors/{major_id}", dependencies=[Depends(require_staff)])
def update_major(
    major_id: UUID, payload: MajorUpdate, db: Session = Depends(get_db),
) -> dict:
    major = db.get(Major, major_id)
    if major is None:
        raise AppError(404, "MAJOR_NOT_FOUND", "Không tìm thấy ngành.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(major, field, value)
    db.commit()
    db.refresh(major)
    return success_response(
        {"id": str(major.id), "department_id": str(major.department_id), "code": major.code, "name": major.name, "is_active": major.is_active},
        "Cập nhật ngành thành công."
    )
