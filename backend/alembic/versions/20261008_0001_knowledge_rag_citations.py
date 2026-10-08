"""knowledge ingestion errors and AI answer citations

Revision ID: 20261008_0001
Revises: 20260929_0001
Create Date: 2026-10-08
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261008_0001"
down_revision: str | None = "20260929_0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("knowledge_sources", sa.Column("processing_error", sa.Text(), nullable=True))
    op.add_column("ai_responses", sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_responses", "citations")
    op.drop_column("knowledge_sources", "processing_error")
