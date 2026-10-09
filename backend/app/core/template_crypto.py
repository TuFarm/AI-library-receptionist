"""Application-layer encryption for face templates (`face_profiles.face_template_encrypted`).

Stored layout: MAGIC | key id (4 bytes) | nonce (12 bytes) | AES-256-GCM ciphertext+tag.
The owning user's id is bound as associated data, so a template copied onto another
user's row does not decrypt. Losing FACE_TEMPLATE_KEY makes every template unreadable;
visitors then have to re-enroll.
"""
import hashlib
import logging
import os
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

logger = logging.getLogger(__name__)

MAGIC = b"FT1"
_KEY_ID_LEN = 4
_NONCE_LEN = 12


class TemplateKeyMissing(RuntimeError):
    pass


def _key() -> bytes | None:
    return settings.face_template_key_bytes


def _key_id(key: bytes) -> bytes:
    return hashlib.sha256(key).digest()[:_KEY_ID_LEN]


def _aad(user_id: UUID) -> bytes:
    return b"face-template:" + user_id.bytes


def is_encrypted(stored: bytes | None) -> bool:
    return bool(stored) and stored.startswith(MAGIC)


def encrypt_template(user_id: UUID, raw: bytes | None) -> bytes | None:
    if raw is None:
        return None
    key = _key()
    if key is None:
        if settings.is_production:
            raise TemplateKeyMissing("FACE_TEMPLATE_KEY is required to store face templates in production")
        return raw  # development without a key keeps the legacy plaintext format
    nonce = os.urandom(_NONCE_LEN)
    return MAGIC + _key_id(key) + nonce + AESGCM(key).encrypt(nonce, raw, _aad(user_id))


def decrypt_template(profile_id: UUID | None, user_id: UUID, stored: bytes | None) -> bytes | None:
    """Plain template bytes, or None when the row cannot be used (logged by profile id only)."""
    if not stored:
        return stored
    if not is_encrypted(stored):
        if settings.is_production:
            logger.warning("Skipping unencrypted face template on profile %s; run scripts/encrypt_face_templates.py", profile_id)
            return None
        return stored
    key = _key()
    if key is None:
        logger.warning("Skipping encrypted face template on profile %s: FACE_TEMPLATE_KEY is not set", profile_id)
        return None
    header = len(MAGIC)
    if stored[header:header + _KEY_ID_LEN] != _key_id(key):
        logger.warning("Skipping face template on profile %s: encrypted with a different FACE_TEMPLATE_KEY", profile_id)
        return None
    nonce_at = header + _KEY_ID_LEN
    nonce = stored[nonce_at:nonce_at + _NONCE_LEN]
    try:
        return AESGCM(key).decrypt(nonce, stored[nonce_at + _NONCE_LEN:], _aad(user_id))
    except InvalidTag:
        logger.warning("Skipping face template on profile %s: integrity check failed", profile_id)
        return None
