"""Staff accounts and revocable, client-bound admin sessions stored in PostgreSQL."""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.core.security import (
    hash_password, new_session_token, password_needs_rehash, sha256_hex, verify_password,
)
from app.models.schema import StaffAccount, StaffSession

ROLES = ("admin", "librarian")


@lru_cache(maxsize=4)
def _dummy_hash(iterations: int) -> str:
    """Verified for unknown/inactive usernames so both paths cost the same PBKDF2 work."""
    return hash_password("timing-equalizer", iterations)


@dataclass(frozen=True)
class StaffIdentity:
    id: UUID
    username: str
    full_name: str
    role: str
    expires_at: int
    token_hash: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def public(self) -> dict:
        return {"id": str(self.id), "username": self.username, "full_name": self.full_name,
                "role": self.role, "expires_at": self.expires_at}


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    # SQLite (unit tests) returns naive datetimes; PostgreSQL returns aware ones.
    return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


def normalize_username(username: str) -> str:
    return username.strip().lower()


def client_binding(ip: str, device: str, user_agent: str) -> str:
    return sha256_hex(f"{ip}\0{device}\0{user_agent}")


def _password_hash(password: str) -> str:
    return hash_password(password, settings.staff_password_iterations)


def create_staff(db: Session, username: str, full_name: str, role: str, password: str) -> StaffAccount:
    if role not in ROLES:
        raise AppError(422, "INVALID_ROLE", "Vai trò không hợp lệ.")
    username = normalize_username(username)
    if db.scalar(select(StaffAccount.id).where(StaffAccount.username == username)):
        raise AppError(409, "STAFF_USERNAME_EXISTS", "Tên đăng nhập đã được sử dụng.")
    now = _now()
    staff = StaffAccount(username=username, full_name=full_name.strip(), role=role,
                         password_hash=_password_hash(password), is_active=True,
                         failed_login_count=0, password_changed_at=now)
    db.add(staff)
    db.flush()
    return staff


def _identity(staff: StaffAccount, session: StaffSession) -> StaffIdentity:
    return StaffIdentity(staff.id, staff.username, staff.full_name, staff.role,
                         int(_aware(session.expires_at).timestamp()), session.token_hash)


def login(db: Session, username: str, password: str, binding: str) -> tuple[str, StaffIdentity]:
    now = _now()
    staff = db.scalar(select(StaffAccount).where(StaffAccount.username == normalize_username(username)))
    if staff is None or not staff.is_active:
        verify_password(password, _dummy_hash(settings.staff_password_iterations))
        raise AppError(403, "ADMIN_ACCESS_DENIED", "Tên đăng nhập hoặc mật khẩu không đúng.")
    locked_until = _aware(staff.locked_until)
    if locked_until and locked_until > now:
        raise AppError(429, "ADMIN_ACCOUNT_LOCKED",
                       "Tài khoản tạm khóa do đăng nhập sai nhiều lần. Vui lòng thử lại sau.")
    if not verify_password(password, staff.password_hash):
        staff.failed_login_count = (staff.failed_login_count or 0) + 1
        if staff.failed_login_count >= settings.staff_login_max_failures:
            staff.locked_until = now + timedelta(minutes=settings.staff_login_lockout_minutes)
            staff.failed_login_count = 0
        db.commit()
        raise AppError(403, "ADMIN_ACCESS_DENIED", "Tên đăng nhập hoặc mật khẩu không đúng.")

    staff.failed_login_count = 0
    staff.locked_until = None
    staff.last_login_at = now
    if password_needs_rehash(staff.password_hash, settings.staff_password_iterations):
        staff.password_hash = _password_hash(password)
    db.execute(delete(StaffSession).where(StaffSession.expires_at <= now))
    token = new_session_token()
    session = StaffSession(staff_id=staff.id, token_hash=sha256_hex(token), binding_hash=binding,
                           created_at=now, expires_at=now + timedelta(minutes=settings.staff_session_minutes))
    db.add(session)
    db.commit()
    return token, _identity(staff, session)


def read_session(db: Session, token: str, binding: str) -> StaffIdentity:
    row = db.execute(select(StaffSession, StaffAccount).join(StaffAccount).where(
        StaffSession.token_hash == sha256_hex(token))).first()
    if row is None:
        raise AppError(401, "ADMIN_SESSION_EXPIRED", "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.")
    session, staff = row
    if session.revoked_at is not None or _aware(session.expires_at) <= _now() or not staff.is_active:
        raise AppError(401, "ADMIN_SESSION_EXPIRED", "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.")
    if session.binding_hash != binding:
        raise AppError(401, "ADMIN_SESSION_INVALID", "IP hoặc thiết bị đã thay đổi. Vui lòng đăng nhập lại.")
    return _identity(staff, session)


def revoke_session(db: Session, token_hash: str) -> None:
    db.execute(update(StaffSession).where(StaffSession.token_hash == token_hash,
                                          StaffSession.revoked_at.is_(None)).values(revoked_at=_now()))
    db.commit()


def revoke_all_sessions(db: Session, staff_id: UUID) -> None:
    db.execute(update(StaffSession).where(StaffSession.staff_id == staff_id,
                                          StaffSession.revoked_at.is_(None)).values(revoked_at=_now()))


def change_password(db: Session, staff_id: UUID, current_password: str, new_password: str) -> None:
    staff = db.get(StaffAccount, staff_id)
    if staff is None or not verify_password(current_password, staff.password_hash):
        raise AppError(403, "ADMIN_ACCESS_DENIED", "Mật khẩu hiện tại không đúng.")
    if current_password == new_password:
        raise AppError(422, "PASSWORD_UNCHANGED", "Mật khẩu mới phải khác mật khẩu hiện tại.")
    staff.password_hash = _password_hash(new_password)
    staff.password_changed_at = _now()
    revoke_all_sessions(db, staff.id)
    db.commit()


def _active_admin_count(db: Session) -> int:
    return db.scalar(select(func.count(StaffAccount.id)).where(
        StaffAccount.role == "admin", StaffAccount.is_active.is_(True))) or 0


def update_staff(db: Session, actor: StaffIdentity, staff: StaffAccount, *, full_name: str | None = None,
                 role: str | None = None, is_active: bool | None = None) -> StaffAccount:
    demoting = role is not None and role != "admin" and staff.role == "admin"
    deactivating = is_active is False and staff.is_active
    if staff.id == actor.id and (demoting or deactivating):
        raise AppError(409, "CANNOT_CHANGE_OWN_ACCESS",
                       "Không thể tự hạ quyền hoặc vô hiệu hóa tài khoản đang đăng nhập.")
    if (demoting or (deactivating and staff.role == "admin")) and _active_admin_count(db) <= 1:
        raise AppError(409, "LAST_ADMIN", "Hệ thống cần ít nhất một quản trị viên đang hoạt động.")
    if role is not None and role not in ROLES:
        raise AppError(422, "INVALID_ROLE", "Vai trò không hợp lệ.")
    if full_name is not None:
        staff.full_name = full_name.strip()
    if role is not None and role != staff.role:
        staff.role = role
        revoke_all_sessions(db, staff.id)
    if is_active is not None and is_active != staff.is_active:
        staff.is_active = is_active
        if not is_active:
            revoke_all_sessions(db, staff.id)
    db.commit()
    db.refresh(staff)
    return staff


def reset_password(db: Session, staff: StaffAccount, new_password: str) -> None:
    staff.password_hash = _password_hash(new_password)
    staff.password_changed_at = _now()
    staff.failed_login_count = 0
    staff.locked_until = None
    revoke_all_sessions(db, staff.id)
    db.commit()


def staff_data(staff: StaffAccount) -> dict:
    locked_until = _aware(staff.locked_until)
    return {"id": str(staff.id), "username": staff.username, "full_name": staff.full_name, "role": staff.role,
            "is_active": staff.is_active, "locked": bool(locked_until and locked_until > _now()),
            "last_login_at": _aware(staff.last_login_at).isoformat() if staff.last_login_at else None,
            "created_at": _aware(staff.created_at).isoformat() if staff.created_at else None}
