"""idempotency keys for Face ID enrollment

Revision ID: 20261010_0001
Revises: 20261009_0001
Create Date: 2026-10-10
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261010_0001"
down_revision: str | None = "20261009_0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "face_enrollment_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_key", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("face_profile_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("face_profiles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_face_enrollment_requests_device_id", "face_enrollment_requests", ["device_id"])
    op.create_index("ix_face_enrollment_requests_user_id", "face_enrollment_requests", ["user_id"])
    op.create_index("ix_face_enrollment_requests_created_at", "face_enrollment_requests", ["created_at"])


def downgrade() -> None:
    op.drop_table("face_enrollment_requests")
