"""record explicit Face ID consent on users

Revision ID: 20261009_0001
Revises: 20261008_0001
Create Date: 2026-10-09
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261009_0001"
down_revision: str | None = "20261008_0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("face_consent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("face_consent_version", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "face_consent_version")
    op.drop_column("users", "face_consent_at")
