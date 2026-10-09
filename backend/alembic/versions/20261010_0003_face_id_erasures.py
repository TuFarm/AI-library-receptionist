"""audit log of Face ID erasures (kiosk self-service and admin at the desk)

Revision ID: 20261010_0003
Revises: 20261010_0002
Create Date: 2026-10-10
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261010_0003"
down_revision: str | None = "20261010_0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "face_id_erasures",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("staff_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("staff_accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("staff_username", sa.String(length=100), nullable=True),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("deleted_profiles", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("source IN ('KIOSK', 'ADMIN')"),
    )
    op.create_index("ix_face_id_erasures_user_id", "face_id_erasures", ["user_id"])
    op.create_index("ix_face_id_erasures_created_at", "face_id_erasures", ["created_at"])


def downgrade() -> None:
    op.drop_table("face_id_erasures")
