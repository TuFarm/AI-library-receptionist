"""Department and major domain services.

Provides seed data and input normalization for academic lookup tables.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.schema import Department, Major

# NLU (Nong Lam University) standard departments and majors.
_SEED_DATA: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("CNTT", "Công nghệ Thông tin", [
        ("CNTT-KTPM", "Kỹ thuật Phần mềm"),
        ("CNTT-KHMT", "Khoa học Máy tính"),
        ("CNTT-HTTT", "Hệ thống Thông tin"),
        ("CNTT-MMT", "Mạng Máy tính và Truyền thông"),
    ]),
    ("CNSH", "Công nghệ Sinh học", [
        ("CNSH-CNSH", "Công nghệ Sinh học"),
    ]),
    ("NH", "Nông học", [
        ("NH-KHCT", "Khoa học Cây trồng"),
        ("NH-BVTV", "Bảo vệ Thực vật"),
    ]),
    ("CN", "Chăn nuôi", [
        ("CN-CNTY", "Chăn nuôi — Thú y"),
    ]),
    ("TS", "Thuỷ sản", [
        ("TS-NTTS", "Nuôi trồng Thuỷ sản"),
    ]),
    ("MT", "Môi trường và Tài nguyên", [
        ("MT-KHMT", "Khoa học Môi trường"),
        ("MT-QLMT", "Quản lý Môi trường"),
    ]),
    ("LN", "Lâm nghiệp", [
        ("LN-LN", "Lâm nghiệp"),
        ("LN-QLTNR", "Quản lý Tài nguyên rừng"),
    ]),
    ("KT", "Kinh tế", [
        ("KT-QTKD", "Quản trị Kinh doanh"),
        ("KT-KT", "Kế toán"),
        ("KT-KTNN", "Kinh tế Nông nghiệp"),
    ]),
    ("CK", "Cơ khí — Công nghệ", [
        ("CK-CNOT", "Công nghệ Ô tô"),
        ("CK-CKCN", "Cơ khí Chế tạo"),
        ("CK-DT", "Điện tử — Viễn thông"),
    ]),
    ("NN", "Ngoại ngữ", [
        ("NN-NNTA", "Ngôn ngữ Anh"),
    ]),
]


def seed_departments(db: Session) -> dict:
    """Insert seed departments and majors if they don't exist.
    
    Returns a summary of what was created.
    """
    created_depts = 0
    created_majors = 0

    for dept_code, dept_name, majors in _SEED_DATA:
        existing_dept = db.scalar(
            select(Department).where(Department.code == dept_code)
        )
        if existing_dept is None:
            dept = Department(code=dept_code, name=dept_name)
            db.add(dept)
            db.flush()  # Get ID for foreign key
            created_depts += 1
        else:
            dept = existing_dept

        for major_code, major_name in majors:
            existing_major = db.scalar(
                select(Major).where(Major.code == major_code)
            )
            if existing_major is None:
                db.add(Major(
                    department_id=dept.id,
                    code=major_code,
                    name=major_name,
                ))
                created_majors += 1

    db.commit()
    return {"departments_created": created_depts, "majors_created": created_majors}


def normalize_lookup(db: Session, input_text: str) -> dict | None:
    """Attempt to resolve a user input string to a department or major.
    
    Tries exact code match first, then ILIKE name match.
    Returns {"type": "department"|"major", "code": ..., "name": ...} or None.
    """
    normalized = input_text.strip().upper()
    
    # Try exact major code
    major = db.scalar(select(Major).where(Major.code == normalized, Major.is_active.is_(True)))
    if major:
        return {"type": "major", "code": major.code, "name": major.name, "id": str(major.id)}
    
    # Try exact department code
    dept = db.scalar(select(Department).where(Department.code == normalized, Department.is_active.is_(True)))
    if dept:
        return {"type": "department", "code": dept.code, "name": dept.name, "id": str(dept.id)}
    
    # Try ILIKE name match for major
    term = f"%{input_text.strip()}%"
    major = db.scalar(select(Major).where(Major.name.ilike(term), Major.is_active.is_(True)))
    if major:
        return {"type": "major", "code": major.code, "name": major.name, "id": str(major.id)}
    
    # Try ILIKE name match for department
    dept = db.scalar(select(Department).where(Department.name.ilike(term), Department.is_active.is_(True)))
    if dept:
        return {"type": "department", "code": dept.code, "name": dept.name, "id": str(dept.id)}
    
    return None
