"""stop storing student phone numbers

Revision ID: 20261010_0002
Revises: 20261010_0001
Create Date: 2026-10-10

Upgrading deletes every stored phone number; a downgrade restores only the empty column.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261010_0002"
down_revision: str | None = "20261010_0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("users", "phone")


def downgrade() -> None:
    op.add_column("users", sa.Column("phone", sa.String(length=30), nullable=True))
