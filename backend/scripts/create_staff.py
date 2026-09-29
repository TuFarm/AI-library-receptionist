"""Create a staff account (e.g. the first admin). Run from backend:

    python scripts/create_staff.py --username admin --full-name "Quản trị viên" --role admin

The password is read from the STAFF_PASSWORD environment variable when set
(for non-interactive deploys), otherwise prompted without echo.
"""
import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import ValidationError  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.core.errors import AppError  # noqa: E402
from app.schemas.auth import StaffCreate  # noqa: E402
from app.services.staff_auth_service import create_staff  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a staff account for the admin UI.")
    parser.add_argument("--username", required=True)
    parser.add_argument("--full-name", required=True)
    parser.add_argument("--role", choices=("admin", "librarian"), default="admin")
    args = parser.parse_args()

    password = os.environ.get("STAFF_PASSWORD")
    if not password:
        password = getpass.getpass("Mật khẩu (8-128 ký tự): ")
        if password != getpass.getpass("Nhập lại mật khẩu: "):
            print("Mật khẩu xác nhận không khớp.", file=sys.stderr)
            return 1
    try:
        payload = StaffCreate(username=args.username, full_name=args.full_name, role=args.role, password=password)
    except ValidationError as exc:
        for error in exc.errors():
            print(f"{'.'.join(map(str, error['loc']))}: {error['msg']}", file=sys.stderr)
        return 1
    with SessionLocal() as db:
        try:
            staff = create_staff(db, payload.username, payload.full_name, payload.role, payload.password)
            db.commit()
        except AppError as exc:
            print(exc.message, file=sys.stderr)
            return 1
        print(f"Đã tạo tài khoản {staff.username} ({staff.role}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
