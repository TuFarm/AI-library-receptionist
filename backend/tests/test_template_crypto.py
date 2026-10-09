"""Face templates are encrypted at rest, bound to their owner, and fail closed."""
import base64
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core import template_crypto
from app.core.config import Settings, settings
from app.core.template_crypto import decrypt_template, encrypt_template, is_encrypted

OTHER_KEY = base64.b64encode(bytes(range(100, 132))).decode()
RAW = b"[0.25, -0.5, 1.0]"


def test_round_trip_hides_the_template():
    user_id = uuid4()
    stored = encrypt_template(user_id, RAW)
    assert is_encrypted(stored) and RAW not in stored
    assert decrypt_template(uuid4(), user_id, stored) == RAW
    assert encrypt_template(user_id, RAW) != stored  # fresh nonce per write


def test_template_copied_to_another_user_does_not_decrypt():
    stored = encrypt_template(uuid4(), RAW)
    assert decrypt_template(uuid4(), uuid4(), stored) is None


def test_wrong_or_missing_key_fails_closed(monkeypatch):
    user_id = uuid4()
    stored = encrypt_template(user_id, RAW)
    monkeypatch.setattr(settings, "face_template_key", OTHER_KEY)
    assert decrypt_template(uuid4(), user_id, stored) is None
    monkeypatch.setattr(settings, "face_template_key", "")
    assert decrypt_template(uuid4(), user_id, stored) is None


def test_tampered_ciphertext_is_rejected():
    user_id = uuid4()
    stored = bytearray(encrypt_template(user_id, RAW))
    stored[-1] ^= 1
    assert decrypt_template(uuid4(), user_id, bytes(stored)) is None


def test_plaintext_rows_are_accepted_only_outside_production(monkeypatch):
    assert decrypt_template(uuid4(), uuid4(), RAW) == RAW
    monkeypatch.setattr(settings, "environment", "production")
    assert decrypt_template(uuid4(), uuid4(), RAW) is None


def test_production_refuses_to_store_without_a_key(monkeypatch):
    monkeypatch.setattr(settings, "face_template_key", "")
    assert encrypt_template(uuid4(), RAW) == RAW  # development keeps working
    monkeypatch.setattr(settings, "environment", "production")
    with pytest.raises(template_crypto.TemplateKeyMissing):
        encrypt_template(uuid4(), RAW)


def test_settings_validate_the_key():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, face_template_key="not base64!")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, face_template_key=base64.b64encode(b"short").decode())
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="production", face_template_key="")
    assert Settings(_env_file=None, environment="production", face_template_key=OTHER_KEY).is_production


def test_encrypt_script_converts_legacy_rows_once(sqlite_db):
    import importlib.util
    from datetime import UTC, datetime
    from pathlib import Path

    from app.models.schema import FaceProfile, User

    spec = importlib.util.spec_from_file_location(
        "encrypt_face_templates", Path(__file__).resolve().parents[1] / "scripts" / "encrypt_face_templates.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)

    user = User(full_name="Legacy", user_type="STUDENT", account_status="ACTIVE", preferred_language="vi")
    sqlite_db.add(user)
    sqlite_db.flush()
    profile = FaceProfile(user_id=user.id, face_template_encrypted=RAW, enrolled_at=datetime.now(UTC), active=True)
    sqlite_db.add(profile)
    sqlite_db.commit()

    assert script.encrypt_plaintext_templates(sqlite_db, dry_run=True) == (1, 0)
    sqlite_db.refresh(profile)
    assert profile.face_template_encrypted == RAW
    assert script.encrypt_plaintext_templates(sqlite_db) == (1, 0)
    sqlite_db.refresh(profile)
    assert decrypt_template(profile.id, user.id, profile.face_template_encrypted) == RAW
    assert script.encrypt_plaintext_templates(sqlite_db) == (0, 1)
