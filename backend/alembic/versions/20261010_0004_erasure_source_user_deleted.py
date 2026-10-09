"""allow USER_DELETED as a Face ID erasure source (profile deletion erases the Face ID)

Revision ID: 20261010_0004
Revises: 20261010_0003
Create Date: 2026-10-10
"""
from collections.abc import Sequence

from alembic import op

revision: str = "20261010_0004"
down_revision: str | None = "20261010_0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # 20261010_0003 created the check without a name; PostgreSQL named it <table>_<column>_check.
    op.execute("ALTER TABLE face_id_erasures DROP CONSTRAINT IF EXISTS face_id_erasures_source_check")
    op.create_check_constraint("ck_face_id_erasures_source", "face_id_erasures",
                               "source IN ('KIOSK', 'ADMIN', 'USER_DELETED')")


def downgrade() -> None:
    # The old constraint cannot hold USER_DELETED rows; those audit rows are lost on downgrade.
    op.execute("DELETE FROM face_id_erasures WHERE source = 'USER_DELETED'")
    op.drop_constraint("ck_face_id_erasures_source", "face_id_erasures", type_="check")
    op.create_check_constraint("face_id_erasures_source_check", "face_id_erasures", "source IN ('KIOSK', 'ADMIN')")
