"""initial AI kiosk assistant schema (24 tables)

Revision ID: 20260902_0001
Revises:
Create Date: 2026-09-02

The DDL is frozen here instead of being created from the live ORM metadata.
Later model changes must ship in their own migrations; otherwise a fresh
database and an upgraded database would silently diverge.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260902_0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('book_categories',
    sa.Column('category_name', sa.String(length=150), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('category_name')
    )
    op.create_table('daily_report_metrics',
    sa.Column('report_date', sa.Date(), nullable=False),
    sa.Column('total_sessions', sa.Integer(), nullable=False),
    sa.Column('total_identified_users', sa.Integer(), nullable=False),
    sa.Column('total_questions', sa.Integer(), nullable=False),
    sa.Column('total_ai_answers', sa.Integer(), nullable=False),
    sa.Column('total_surveys', sa.Integer(), nullable=False),
    sa.Column('avg_satisfaction_score', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('avg_ai_response_time_ms', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('avg_ai_response_time_ms IS NULL OR avg_ai_response_time_ms >= 0'),
    sa.CheckConstraint('avg_satisfaction_score IS NULL OR avg_satisfaction_score BETWEEN 1 AND 5'),
    sa.CheckConstraint('total_sessions >= 0 AND total_identified_users >= 0 AND total_questions >= 0 AND total_ai_answers >= 0 AND total_surveys >= 0'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_daily_report_metrics_report_date'), 'daily_report_metrics', ['report_date'], unique=True)
    op.create_table('devices',
    sa.Column('device_code', sa.String(length=80), nullable=False),
    sa.Column('device_name', sa.String(length=150), nullable=False),
    sa.Column('location', sa.String(length=255), nullable=True),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('device_code')
    )
    op.create_index(op.f('ix_devices_location'), 'devices', ['location'], unique=False)
    op.create_index(op.f('ix_devices_status'), 'devices', ['status'], unique=False)
    op.create_table('prompt_versions',
    sa.Column('prompt_name', sa.String(length=150), nullable=False),
    sa.Column('version_number', sa.Integer(), nullable=False),
    sa.Column('prompt_text', sa.Text(), nullable=False),
    sa.Column('change_reason', sa.Text(), nullable=True),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.CheckConstraint('version_number > 0'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('prompt_name', 'version_number')
    )
    op.create_index(op.f('ix_prompt_versions_active'), 'prompt_versions', ['active'], unique=False)
    op.create_index(op.f('ix_prompt_versions_prompt_name'), 'prompt_versions', ['prompt_name'], unique=False)
    op.create_table('surveys',
    sa.Column('survey_name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('version > 0'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('survey_name', 'version')
    )
    op.create_index(op.f('ix_surveys_active'), 'surveys', ['active'], unique=False)
    op.create_table('users',
    sa.Column('student_code', sa.String(length=50), nullable=True),
    sa.Column('full_name', sa.String(length=255), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=True),
    sa.Column('phone', sa.String(length=30), nullable=True),
    sa.Column('user_type', sa.String(length=30), nullable=False),
    sa.Column('account_status', sa.String(length=30), nullable=False),
    sa.Column('preferred_language', sa.String(length=10), nullable=True),
    sa.Column('faculty', sa.String(length=150), nullable=True),
    sa.Column('major', sa.String(length=150), nullable=True),
    sa.Column('admission_year', sa.Integer(), nullable=True),
    sa.Column('student_level_label', sa.String(length=80), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('admission_year IS NULL OR admission_year >= 1990'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_account_status'), 'users', ['account_status'], unique=False)
    op.create_index(op.f('ix_users_admission_year'), 'users', ['admission_year'], unique=False)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_faculty'), 'users', ['faculty'], unique=False)
    op.create_index(op.f('ix_users_major'), 'users', ['major'], unique=False)
    op.create_index(op.f('ix_users_student_code'), 'users', ['student_code'], unique=True)
    op.create_index(op.f('ix_users_user_type'), 'users', ['user_type'], unique=False)
    op.create_table('face_profiles',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('face_template_ref', sa.String(length=1000), nullable=True),
    sa.Column('face_template_encrypted', sa.LargeBinary(), nullable=True),
    sa.Column('model_name', sa.String(length=120), nullable=True),
    sa.Column('model_version', sa.String(length=80), nullable=True),
    sa.Column('quality_score', sa.Numeric(precision=5, scale=4), nullable=True),
    sa.Column('enrolled_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('face_template_ref IS NOT NULL OR face_template_encrypted IS NOT NULL'),
    sa.CheckConstraint('quality_score IS NULL OR quality_score BETWEEN 0 AND 1'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_face_profiles_user_id'), 'face_profiles', ['user_id'], unique=False)
    op.create_table('knowledge_sources',
    sa.Column('source_name', sa.String(length=255), nullable=False),
    sa.Column('source_type', sa.String(length=40), nullable=False),
    sa.Column('original_file_name', sa.String(length=500), nullable=True),
    sa.Column('file_mime_type', sa.String(length=150), nullable=True),
    sa.Column('file_size', sa.Integer(), nullable=True),
    sa.Column('source_url', sa.Text(), nullable=True),
    sa.Column('storage_path', sa.Text(), nullable=True),
    sa.Column('uploaded_by_user_id', sa.UUID(), nullable=True),
    sa.Column('status', sa.String(length=40), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('file_size IS NULL OR file_size >= 0'),
    sa.ForeignKeyConstraint(['uploaded_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_knowledge_sources_source_type'), 'knowledge_sources', ['source_type'], unique=False)
    op.create_index(op.f('ix_knowledge_sources_status'), 'knowledge_sources', ['status'], unique=False)
    op.create_index(op.f('ix_knowledge_sources_uploaded_by_user_id'), 'knowledge_sources', ['uploaded_by_user_id'], unique=False)
    op.create_table('suggested_books',
    sa.Column('category_id', sa.UUID(), nullable=True),
    sa.Column('external_book_id', sa.String(length=120), nullable=True),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('author_name', sa.String(length=255), nullable=True),
    sa.Column('short_description', sa.Text(), nullable=True),
    sa.Column('source', sa.String(length=255), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['category_id'], ['book_categories.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_suggested_books_category_id'), 'suggested_books', ['category_id'], unique=False)
    op.create_index(op.f('ix_suggested_books_external_book_id'), 'suggested_books', ['external_book_id'], unique=False)
    op.create_index(op.f('ix_suggested_books_title'), 'suggested_books', ['title'], unique=False)
    op.create_table('survey_questions',
    sa.Column('survey_id', sa.UUID(), nullable=False),
    sa.Column('question_text', sa.Text(), nullable=False),
    sa.Column('question_type', sa.String(length=30), nullable=False),
    sa.Column('question_order', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.CheckConstraint('question_order > 0'),
    sa.ForeignKeyConstraint(['survey_id'], ['surveys.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('survey_id', 'question_order')
    )
    op.create_index(op.f('ix_survey_questions_survey_id'), 'survey_questions', ['survey_id'], unique=False)
    op.create_table('user_preferences',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('favorite_category', sa.String(length=150), nullable=True),
    sa.Column('favorite_topics', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('preferred_response_style', sa.String(length=80), nullable=True),
    sa.Column('preferred_input_method', sa.String(length=30), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id')
    )
    op.create_table('user_sessions',
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('device_id', sa.UUID(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('duration_seconds', sa.Integer(), nullable=True),
    sa.Column('identified', sa.Boolean(), nullable=False),
    sa.Column('exit_reason', sa.String(length=40), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('duration_seconds IS NULL OR duration_seconds >= 0'),
    sa.CheckConstraint('ended_at IS NULL OR ended_at >= started_at'),
    sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_sessions_device_id'), 'user_sessions', ['device_id'], unique=False)
    op.create_index('ix_user_sessions_device_started', 'user_sessions', ['device_id', 'started_at'], unique=False)
    op.create_index(op.f('ix_user_sessions_started_at'), 'user_sessions', ['started_at'], unique=False)
    op.create_index(op.f('ix_user_sessions_user_id'), 'user_sessions', ['user_id'], unique=False)
    op.create_table('book_suggestion_logs',
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('session_id', sa.UUID(), nullable=True),
    sa.Column('category_id', sa.UUID(), nullable=True),
    sa.Column('suggested_book_id', sa.UUID(), nullable=True),
    sa.Column('shown_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('clicked', sa.Boolean(), nullable=True),
    sa.Column('feedback_score', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.CheckConstraint('feedback_score IS NULL OR feedback_score BETWEEN 1 AND 5'),
    sa.ForeignKeyConstraint(['category_id'], ['book_categories.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['session_id'], ['user_sessions.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['suggested_book_id'], ['suggested_books.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_book_suggestion_logs_session_id'), 'book_suggestion_logs', ['session_id'], unique=False)
    op.create_index(op.f('ix_book_suggestion_logs_shown_at'), 'book_suggestion_logs', ['shown_at'], unique=False)
    op.create_index(op.f('ix_book_suggestion_logs_user_id'), 'book_suggestion_logs', ['user_id'], unique=False)
    op.create_index('ix_book_suggestion_session_shown', 'book_suggestion_logs', ['session_id', 'shown_at'], unique=False)
    op.create_table('conversations',
    sa.Column('session_id', sa.UUID(), nullable=True),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('ended_at IS NULL OR ended_at >= started_at'),
    sa.ForeignKeyConstraint(['session_id'], ['user_sessions.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_conversations_session_id'), 'conversations', ['session_id'], unique=False)
    op.create_index(op.f('ix_conversations_status'), 'conversations', ['status'], unique=False)
    op.create_index(op.f('ix_conversations_user_id'), 'conversations', ['user_id'], unique=False)
    op.create_table('face_authentication_logs',
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('session_id', sa.UUID(), nullable=True),
    sa.Column('device_id', sa.UUID(), nullable=True),
    sa.Column('result', sa.String(length=40), nullable=False),
    sa.Column('confidence_score', sa.Numeric(precision=5, scale=4), nullable=True),
    sa.Column('processing_time_ms', sa.Integer(), nullable=True),
    sa.Column('attempt_number', sa.Integer(), nullable=False),
    sa.Column('failure_reason', sa.String(length=255), nullable=True),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.CheckConstraint('attempt_number > 0'),
    sa.CheckConstraint('confidence_score IS NULL OR confidence_score BETWEEN 0 AND 1'),
    sa.CheckConstraint('processing_time_ms IS NULL OR processing_time_ms >= 0'),
    sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['session_id'], ['user_sessions.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_face_auth_session_time', 'face_authentication_logs', ['session_id', 'occurred_at'], unique=False)
    op.create_index(op.f('ix_face_authentication_logs_device_id'), 'face_authentication_logs', ['device_id'], unique=False)
    op.create_index(op.f('ix_face_authentication_logs_occurred_at'), 'face_authentication_logs', ['occurred_at'], unique=False)
    op.create_index(op.f('ix_face_authentication_logs_result'), 'face_authentication_logs', ['result'], unique=False)
    op.create_index(op.f('ix_face_authentication_logs_session_id'), 'face_authentication_logs', ['session_id'], unique=False)
    op.create_index(op.f('ix_face_authentication_logs_user_id'), 'face_authentication_logs', ['user_id'], unique=False)
    op.create_table('interaction_events',
    sa.Column('session_id', sa.UUID(), nullable=True),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('device_id', sa.UUID(), nullable=True),
    sa.Column('event_type', sa.String(length=80), nullable=False),
    sa.Column('event_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('input_method', sa.String(length=30), nullable=True),
    sa.Column('content_summary', sa.Text(), nullable=True),
    sa.Column('success', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['session_id'], ['user_sessions.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_interaction_events_device_id'), 'interaction_events', ['device_id'], unique=False)
    op.create_index(op.f('ix_interaction_events_event_time'), 'interaction_events', ['event_time'], unique=False)
    op.create_index(op.f('ix_interaction_events_event_type'), 'interaction_events', ['event_type'], unique=False)
    op.create_index(op.f('ix_interaction_events_session_id'), 'interaction_events', ['session_id'], unique=False)
    op.create_index(op.f('ix_interaction_events_user_id'), 'interaction_events', ['user_id'], unique=False)
    op.create_index('ix_interaction_session_time', 'interaction_events', ['session_id', 'event_time'], unique=False)
    op.create_index('ix_interaction_type_time', 'interaction_events', ['event_type', 'event_time'], unique=False)
    op.create_table('knowledge_documents',
    sa.Column('source_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('document_type', sa.String(length=80), nullable=True),
    sa.Column('language', sa.String(length=10), nullable=True),
    sa.Column('version', sa.String(length=50), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('processing_status', sa.String(length=40), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['source_id'], ['knowledge_sources.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_knowledge_documents_is_active'), 'knowledge_documents', ['is_active'], unique=False)
    op.create_index(op.f('ix_knowledge_documents_processing_status'), 'knowledge_documents', ['processing_status'], unique=False)
    op.create_index(op.f('ix_knowledge_documents_source_id'), 'knowledge_documents', ['source_id'], unique=False)
    op.create_table('survey_responses',
    sa.Column('survey_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('session_id', sa.UUID(), nullable=True),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['user_sessions.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['survey_id'], ['surveys.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_survey_response_session_time', 'survey_responses', ['session_id', 'submitted_at'], unique=False)
    op.create_index(op.f('ix_survey_responses_session_id'), 'survey_responses', ['session_id'], unique=False)
    op.create_index(op.f('ix_survey_responses_submitted_at'), 'survey_responses', ['submitted_at'], unique=False)
    op.create_index(op.f('ix_survey_responses_survey_id'), 'survey_responses', ['survey_id'], unique=False)
    op.create_index(op.f('ix_survey_responses_user_id'), 'survey_responses', ['user_id'], unique=False)
    op.create_table('conversation_messages',
    sa.Column('conversation_id', sa.UUID(), nullable=False),
    sa.Column('sender_type', sa.String(length=20), nullable=False),
    sa.Column('message_text', sa.Text(), nullable=True),
    sa.Column('input_method', sa.String(length=30), nullable=True),
    sa.Column('message_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('intent_detected', sa.String(length=120), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_conversation_messages_conversation_id'), 'conversation_messages', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_conversation_messages_message_time'), 'conversation_messages', ['message_time'], unique=False)
    op.create_index(op.f('ix_conversation_messages_sender_type'), 'conversation_messages', ['sender_type'], unique=False)
    op.create_index('ix_message_conversation_time', 'conversation_messages', ['conversation_id', 'message_time'], unique=False)
    op.create_table('knowledge_chunks',
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('chunk_index', sa.Integer(), nullable=False),
    sa.Column('chunk_text', sa.Text(), nullable=False),
    sa.Column('page_number', sa.Integer(), nullable=True),
    sa.Column('sheet_name', sa.String(length=255), nullable=True),
    sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.CheckConstraint('chunk_index >= 0'),
    sa.ForeignKeyConstraint(['document_id'], ['knowledge_documents.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('document_id', 'chunk_index')
    )
    op.create_index(op.f('ix_knowledge_chunks_document_id'), 'knowledge_chunks', ['document_id'], unique=False)
    op.create_table('survey_answers',
    sa.Column('response_id', sa.UUID(), nullable=False),
    sa.Column('question_id', sa.UUID(), nullable=False),
    sa.Column('answer_text', sa.Text(), nullable=True),
    sa.Column('answer_number', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['question_id'], ['survey_questions.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['response_id'], ['survey_responses.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('response_id', 'question_id')
    )
    op.create_index(op.f('ix_survey_answers_question_id'), 'survey_answers', ['question_id'], unique=False)
    op.create_index(op.f('ix_survey_answers_response_id'), 'survey_answers', ['response_id'], unique=False)
    op.create_table('ai_requests',
    sa.Column('conversation_id', sa.UUID(), nullable=True),
    sa.Column('user_message_id', sa.UUID(), nullable=True),
    sa.Column('request_type', sa.String(length=40), nullable=False),
    sa.Column('model_name', sa.String(length=120), nullable=True),
    sa.Column('prompt_version_id', sa.UUID(), nullable=True),
    sa.Column('input_token_count', sa.Integer(), nullable=True),
    sa.Column('output_token_count', sa.Integer(), nullable=True),
    sa.Column('latency_ms', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.CheckConstraint('input_token_count IS NULL OR input_token_count >= 0'),
    sa.CheckConstraint('latency_ms IS NULL OR latency_ms >= 0'),
    sa.CheckConstraint('output_token_count IS NULL OR output_token_count >= 0'),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['prompt_version_id'], ['prompt_versions.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_message_id'], ['conversation_messages.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_ai_request_conversation_created', 'ai_requests', ['conversation_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_ai_requests_conversation_id'), 'ai_requests', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_ai_requests_created_at'), 'ai_requests', ['created_at'], unique=False)
    op.create_index(op.f('ix_ai_requests_request_type'), 'ai_requests', ['request_type'], unique=False)
    op.create_index(op.f('ix_ai_requests_status'), 'ai_requests', ['status'], unique=False)
    op.create_table('ai_responses',
    sa.Column('ai_request_id', sa.UUID(), nullable=False),
    sa.Column('ai_message_id', sa.UUID(), nullable=True),
    sa.Column('response_text', sa.Text(), nullable=True),
    sa.Column('response_summary', sa.Text(), nullable=True),
    sa.Column('grounded', sa.Boolean(), nullable=True),
    sa.Column('confidence_score', sa.Numeric(precision=5, scale=4), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.CheckConstraint('confidence_score IS NULL OR confidence_score BETWEEN 0 AND 1'),
    sa.ForeignKeyConstraint(['ai_message_id'], ['conversation_messages.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['ai_request_id'], ['ai_requests.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ai_responses_ai_request_id'), 'ai_responses', ['ai_request_id'], unique=False)
    op.create_table('ai_feedback',
    sa.Column('ai_response_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('rating_score', sa.Integer(), nullable=True),
    sa.Column('is_helpful', sa.Boolean(), nullable=True),
    sa.Column('is_correct', sa.Boolean(), nullable=True),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.CheckConstraint('rating_score IS NULL OR rating_score BETWEEN 1 AND 5'),
    sa.ForeignKeyConstraint(['ai_response_id'], ['ai_responses.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ai_feedback_ai_response_id'), 'ai_feedback', ['ai_response_id'], unique=False)
    op.create_index(op.f('ix_ai_feedback_user_id'), 'ai_feedback', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_table('ai_feedback')
    op.drop_table('ai_responses')
    op.drop_table('ai_requests')
    op.drop_table('survey_answers')
    op.drop_table('knowledge_chunks')
    op.drop_table('conversation_messages')
    op.drop_table('survey_responses')
    op.drop_table('knowledge_documents')
    op.drop_table('interaction_events')
    op.drop_table('face_authentication_logs')
    op.drop_table('conversations')
    op.drop_table('book_suggestion_logs')
    op.drop_table('user_sessions')
    op.drop_table('user_preferences')
    op.drop_table('survey_questions')
    op.drop_table('suggested_books')
    op.drop_table('knowledge_sources')
    op.drop_table('face_profiles')
    op.drop_table('users')
    op.drop_table('surveys')
    op.drop_table('prompt_versions')
    op.drop_table('devices')
    op.drop_table('daily_report_metrics')
    op.drop_table('book_categories')
