"""Encrypt face templates stored before FACE_TEMPLATE_KEY existed. Run from backend:

    python scripts/encrypt_face_templates.py --dry-run
    python scripts/encrypt_face_templates.py

Safe to repeat: rows that are already encrypted are left alone. In production, unencrypted
rows are ignored by recognition until this has run.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.core.template_crypto import encrypt_template, is_encrypted  # noqa: E402
from app.models.schema import FaceProfile  # noqa: E402


def encrypt_plaintext_templates(db, dry_run: bool = False) -> tuple[int, int]:
    """Return (encrypted now, already encrypted) and commit unless dry_run."""
    pending = already = 0
    for profile in db.scalars(select(FaceProfile).where(FaceProfile.face_template_encrypted.is_not(None))):
        if is_encrypted(profile.face_template_encrypted):
            already += 1
            continue
        pending += 1
        if not dry_run:
            profile.face_template_encrypted = encrypt_template(profile.user_id, profile.face_template_encrypted)
    if dry_run:
        db.rollback()
    else:
        db.commit()
    return pending, already


def main() -> int:
    parser = argparse.ArgumentParser(description="Encrypt plaintext face templates with FACE_TEMPLATE_KEY.")
    parser.add_argument("--dry-run", action="store_true", help="only count rows, change nothing")
    args = parser.parse_args()
    if settings.face_template_key_bytes is None:
        print("FACE_TEMPLATE_KEY is not set; nothing can be encrypted.", file=sys.stderr)
        return 1
    with SessionLocal() as db:
        pending, already = encrypt_plaintext_templates(db, args.dry_run)
    verb = "would encrypt" if args.dry_run else "encrypted"
    print(f"{verb} {pending} template(s); {already} already encrypted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
