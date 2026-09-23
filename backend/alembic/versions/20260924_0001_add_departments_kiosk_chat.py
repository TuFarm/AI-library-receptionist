"""add departments kiosk chat

Revision ID: a1b2c3d4e5f6
Revises: 20260902_0001
Create Date: 2026-09-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '20260902_0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # departments
    op.create_table(
        'departments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('code', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_departments_code'), 'departments', ['code'], unique=True)
    op.create_index(op.f('ix_departments_is_active'), 'departments', ['is_active'], unique=False)

    # majors
    op.create_table(
        'majors',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('department_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('code', sa.String(length=30), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_majors_code'), 'majors', ['code'], unique=True)
    op.create_index(op.f('ix_majors_department_id'), 'majors', ['department_id'], unique=False)
    op.create_index(op.f('ix_majors_is_active'), 'majors', ['is_active'], unique=False)

    # kiosk_devices
    op.create_table(
        'kiosk_devices',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('device_name', sa.String(length=150), nullable=False),
        sa.Column('api_key_hash', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='ACTIVE'),
        sa.Column('last_ping_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_kiosk_devices_api_key_hash'), 'kiosk_devices', ['api_key_hash'], unique=False)
    op.create_index(op.f('ix_kiosk_devices_status'), 'kiosk_devices', ['status'], unique=False)

    # chat_sessions
    op.create_table(
        'chat_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('kiosk_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('major_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['kiosk_id'], ['kiosk_devices.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['major_id'], ['majors.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chat_sessions_kiosk_id'), 'chat_sessions', ['kiosk_id'], unique=False)
    op.create_index(op.f('ix_chat_sessions_major_id'), 'chat_sessions', ['major_id'], unique=False)

    # chat_messages
    op.create_table(
        'chat_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('intent_detected', sa.String(length=120), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('feedback_score', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('feedback_score IS NULL OR feedback_score IN (-1, 1)', name='chat_messages_feedback_score_check'),
        sa.CheckConstraint('latency_ms IS NULL OR latency_ms >= 0', name='chat_messages_latency_ms_check'),
        sa.ForeignKeyConstraint(['session_id'], ['chat_sessions.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_chat_message_session_time', 'chat_messages', ['session_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_chat_messages_session_id'), 'chat_messages', ['session_id'], unique=False)
    op.create_index(op.f('ix_chat_messages_role'), 'chat_messages', ['role'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_chat_messages_role'), table_name='chat_messages')
    op.drop_index(op.f('ix_chat_messages_session_id'), table_name='chat_messages')
    op.drop_index('ix_chat_message_session_time', table_name='chat_messages')
    op.drop_table('chat_messages')
    
    op.drop_index(op.f('ix_chat_sessions_major_id'), table_name='chat_sessions')
    op.drop_index(op.f('ix_chat_sessions_kiosk_id'), table_name='chat_sessions')
    op.drop_table('chat_sessions')
    
    op.drop_index(op.f('ix_kiosk_devices_status'), table_name='kiosk_devices')
    op.drop_index(op.f('ix_kiosk_devices_api_key_hash'), table_name='kiosk_devices')
    op.drop_table('kiosk_devices')
    
    op.drop_index(op.f('ix_majors_is_active'), table_name='majors')
    op.drop_index(op.f('ix_majors_department_id'), table_name='majors')
    op.drop_index(op.f('ix_majors_code'), table_name='majors')
    op.drop_table('majors')
    
    op.drop_index(op.f('ix_departments_is_active'), table_name='departments')
    op.drop_index(op.f('ix_departments_code'), table_name='departments')
    op.drop_table('departments')
