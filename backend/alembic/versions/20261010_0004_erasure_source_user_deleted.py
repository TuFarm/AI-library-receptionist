"""allow USER_DELETED as a Face ID erasure source (profile deletion erases the Face ID)

Revision ID: 20261010_0004
Revises: 20261010_0003
Create Date: 2026-10-10
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "20261010_0004"
down_revision: str | None = "20261010_0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _drop_check_constraints() -> None:
    if context.is_offline_mode():
        # Generating SQL without a database: use PostgreSQL's default name for 20261010_0003's check.
        for name in ("face_id_erasures_source_check", "ck_face_id_erasures_source"):
            op.execute(f"ALTER TABLE face_id_erasures DROP CONSTRAINT IF EXISTS {name}")
        return
    # 20261010_0003 created the check without a name, so look up whatever PostgreSQL called it.
    names = op.get_bind().execute(sa.text(
        "SELECT conname FROM pg_constraint WHERE conrelid = 'face_id_erasures'::regclass AND contype = 'c'"
    )).scalars().all()
    for name in names:
        op.drop_constraint(name, "face_id_erasures", type_="check")


def upgrade() -> None:
    _drop_check_constraints()
    op.create_check_constraint("ck_face_id_erasures_source", "face_id_erasures",
                               "source IN ('KIOSK', 'ADMIN', 'USER_DELETED')")


def downgrade() -> None:
    # The old constraint cannot hold USER_DELETED rows; those audit rows are lost on downgrade.
    op.execute("DELETE FROM face_id_erasures WHERE source = 'USER_DELETED'")
    _drop_check_constraints()
    op.create_check_constraint("face_id_erasures_source_check", "face_id_erasures", "source IN ('KIOSK', 'ADMIN')")
