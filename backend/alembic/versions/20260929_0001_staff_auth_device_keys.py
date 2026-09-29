"""staff accounts, staff sessions and kiosk device keys

Revision ID: 20260929_0001
Revises: a1b2c3d4e5f6
Create Date: 2026-09-29
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260929_0001"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "staff_accounts",
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("failed_login_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("role IN ('admin', 'librarian')"),
        sa.CheckConstraint("failed_login_count >= 0"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_staff_accounts_username"), "staff_accounts", ["username"], unique=True)
    op.create_index(op.f("ix_staff_accounts_role"), "staff_accounts", ["role"], unique=False)
    op.create_index(op.f("ix_staff_accounts_is_active"), "staff_accounts", ["is_active"], unique=False)

    op.create_table(
        "staff_sessions",
        sa.Column("staff_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("binding_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.CheckConstraint("expires_at > created_at"),
        sa.ForeignKeyConstraint(["staff_id"], ["staff_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_staff_sessions_staff_id"), "staff_sessions", ["staff_id"], unique=False)
    op.create_index(op.f("ix_staff_sessions_expires_at"), "staff_sessions", ["expires_at"], unique=False)

    op.add_column("devices", sa.Column("api_key_hash", sa.String(length=64), nullable=True))
    op.add_column("devices", sa.Column("api_key_prefix", sa.String(length=16), nullable=True))
    op.add_column("devices", sa.Column("api_key_rotated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("devices", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint("uq_devices_api_key_hash", "devices", ["api_key_hash"])


def downgrade() -> None:
    op.drop_constraint("uq_devices_api_key_hash", "devices", type_="unique")
    op.drop_column("devices", "last_seen_at")
    op.drop_column("devices", "api_key_rotated_at")
    op.drop_column("devices", "api_key_prefix")
    op.drop_column("devices", "api_key_hash")
    op.drop_index(op.f("ix_staff_sessions_expires_at"), table_name="staff_sessions")
    op.drop_index(op.f("ix_staff_sessions_staff_id"), table_name="staff_sessions")
    op.drop_table("staff_sessions")
    op.drop_index(op.f("ix_staff_accounts_is_active"), table_name="staff_accounts")
    op.drop_index(op.f("ix_staff_accounts_role"), table_name="staff_accounts")
    op.drop_index(op.f("ix_staff_accounts_username"), table_name="staff_accounts")
    op.drop_table("staff_accounts")
