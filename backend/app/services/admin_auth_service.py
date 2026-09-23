"""Persistent staff passwords and revocable, device-bound 15-minute sessions."""
from contextlib import contextmanager
import hashlib
import secrets
import sqlite3
import time

from app.core.config import settings
from app.core.errors import AppError

SESSION_SECONDS = 15 * 60


@contextmanager
def auth_database():
    path = settings.admin_auth_store_path
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.execute("CREATE TABLE IF NOT EXISTS credentials (username TEXT PRIMARY KEY, password_hash TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, username TEXT NOT NULL, binding TEXT NOT NULL, expires_at INTEGER NOT NULL)")
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 600_000)
    return f"{salt}:{digest.hex()}"


def matches(password: str, stored: str) -> bool:
    return secrets.compare_digest(password_hash(password, stored.split(":", 1)[0]), stored)


def ensure_configured():
    if not settings.admin_username or not settings.admin_username.strip() or not settings.admin_password:
        raise AppError(503, "ADMIN_AUTH_NOT_CONFIGURED", "Quyền truy cập quản trị chưa được cấu hình.")


def authenticate(username: str, password: str, db) -> None:
    ensure_configured()
    row = db.execute("SELECT password_hash FROM credentials WHERE username = ?", (settings.admin_username,)).fetchone()
    valid_password = matches(password, row["password_hash"]) if row else secrets.compare_digest(
        password.encode("utf-8"), settings.admin_password.encode("utf-8"))
    if not secrets.compare_digest(username.encode("utf-8"), settings.admin_username.encode("utf-8")) or not valid_password:
        raise AppError(403, "ADMIN_ACCESS_DENIED", "Tên đăng nhập hoặc mật khẩu không đúng.")
    if row is None:
        db.execute("INSERT INTO credentials VALUES (?, ?)", (username, password_hash(password)))


def verify_credentials(username: str, password: str) -> None:
    with auth_database() as db:
        db.execute("BEGIN IMMEDIATE")
        authenticate(username, password, db)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def binding(ip: str, device: str, user_agent: str) -> str:
    return digest(f"{ip}\0{device}\0{user_agent}")


def create_session(username: str, password: str, ip: str, device: str, user_agent: str) -> dict:
    token = secrets.token_urlsafe(32)
    expires = int(time.time()) + SESSION_SECONDS
    with auth_database() as db:
        db.execute("BEGIN IMMEDIATE")
        authenticate(username, password, db)
        db.execute("DELETE FROM sessions WHERE expires_at <= ?", (int(time.time()),))
        db.execute("INSERT INTO sessions VALUES (?, ?, ?, ?)", (digest(token), username, binding(ip, device, user_agent), expires))
    return {"token": token, "username": username, "expires_at": expires}


def read_session(token: str, ip: str, device: str, user_agent: str) -> dict:
    ensure_configured()
    with auth_database() as db:
        row = db.execute("SELECT * FROM sessions WHERE token_hash = ?", (digest(token),)).fetchone()
    if row is None or row["expires_at"] <= time.time():
        raise AppError(401, "ADMIN_SESSION_EXPIRED", "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.")
    if row["username"] != settings.admin_username or not secrets.compare_digest(row["binding"], binding(ip, device, user_agent)):
        raise AppError(401, "ADMIN_SESSION_INVALID", "IP hoặc thiết bị đã thay đổi. Vui lòng đăng nhập lại.")
    return {"username": row["username"], "expires_at": row["expires_at"]}


def revoke_session(token: str) -> None:
    with auth_database() as db:
        db.execute("DELETE FROM sessions WHERE token_hash = ?", (digest(token),))


def change_password(username: str, current_password: str, new_password: str) -> None:
    with auth_database() as db:
        db.execute("BEGIN IMMEDIATE")
        authenticate(username, current_password, db)
        if secrets.compare_digest(current_password.encode("utf-8"), new_password.encode("utf-8")):
            raise AppError(422, "PASSWORD_UNCHANGED", "Mật khẩu mới phải khác mật khẩu hiện tại.")
        db.execute("UPDATE credentials SET password_hash = ? WHERE username = ?", (password_hash(new_password), username))
        db.execute("DELETE FROM sessions WHERE username = ?", (username,))
