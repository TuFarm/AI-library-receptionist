"""Password hashing and opaque-token helpers (stdlib only, no native deps)."""
import hashlib
import hmac
import secrets

PASSWORD_SCHEME = "pbkdf2_sha256"
DEVICE_KEY_PREFIX = "kd_"


def hash_password(password: str, iterations: int) -> str:
    """Return `pbkdf2_sha256$<iterations>$<salt hex>$<digest hex>`."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{PASSWORD_SCHEME}${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt, expected = stored.split("$")
        if scheme != PASSWORD_SCHEME:
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), expected)


def password_needs_rehash(stored: str, iterations: int) -> bool:
    parts = stored.split("$")
    return len(parts) != 4 or parts[0] != PASSWORD_SCHEME or parts[1] != str(iterations)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def new_device_key() -> str:
    """256-bit random key. Its SHA-256 is stored; a slow hash adds nothing at this entropy."""
    return DEVICE_KEY_PREFIX + secrets.token_urlsafe(32)


def device_key_prefix(raw_key: str) -> str:
    """Non-secret prefix shown in the admin UI so staff can tell keys apart."""
    return raw_key[:10]
