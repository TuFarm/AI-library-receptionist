"""Practical 30-table schema for the AI library kiosk assistant."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, SoftDeleteMixin, TimestampMixin

# JSONB on PostgreSQL (what the migrations create); plain JSON on SQLite test databases.
PortableJSON = JSON().with_variant(JSONB(), "postgresql")


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class User(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("admission_year IS NULL OR admission_year >= 1990"),
    )

    student_code: Mapped[str | None] = mapped_column(String(50), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320), unique=True, index=True)
    user_type: Mapped[str] = mapped_column(String(30), index=True)
    account_status: Mapped[str] = mapped_column(String(30), index=True)
    preferred_language: Mapped[str | None] = mapped_column(String(10))
    faculty: Mapped[str | None] = mapped_column(String(150), index=True)
    major: Mapped[str | None] = mapped_column(String(150), index=True)
    admission_year: Mapped[int | None] = mapped_column(Integer, index=True)
    student_level_label: Mapped[str | None] = mapped_column(String(80))
    # Explicit Face ID consent given at enrollment; cleared when the Face ID is erased.
    face_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    face_consent_version: Mapped[str | None] = mapped_column(String(20))

    preferences: Mapped[list[UserPreference]] = relationship(back_populates="user")
    face_profiles: Mapped[list[FaceProfile]] = relationship(back_populates="user")
    sessions: Mapped[list[UserSession]] = relationship(back_populates="user")


class UserPreference(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "user_preferences"
    __table_args__ = (UniqueConstraint("user_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    favorite_category: Mapped[str | None] = mapped_column(String(150))
    favorite_topics: Mapped[list[str] | None] = mapped_column(JSONB)
    preferred_response_style: Mapped[str | None] = mapped_column(String(80))
    preferred_input_method: Mapped[str | None] = mapped_column(String(30))
    note: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User] = relationship(back_populates="preferences")


class FaceProfile(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "face_profiles"
    __table_args__ = (
        CheckConstraint("quality_score IS NULL OR quality_score BETWEEN 0 AND 1"),
        CheckConstraint(
            "face_template_ref IS NOT NULL OR face_template_encrypted IS NOT NULL"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    face_template_ref: Mapped[str | None] = mapped_column(String(1000))
    face_template_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    model_name: Mapped[str | None] = mapped_column(String(120))
    model_version: Mapped[str | None] = mapped_column(String(80))
    quality_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped[User] = relationship(back_populates="face_profiles")


class FaceIdErasure(UUIDPrimaryKeyMixin, Base):
    """Audit trail of every Face ID erasure: by the visitor at a kiosk, or by an admin at the desk."""
    __tablename__ = "face_id_erasures"
    __table_args__ = (CheckConstraint("source IN ('KIOSK', 'ADMIN')"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(10))
    # Snapshot of the admin's username, kept even if the staff account is later removed.
    staff_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("staff_accounts.id", ondelete="SET NULL"))
    staff_username: Mapped[str | None] = mapped_column(String(100))
    device_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"))
    reason: Mapped[str | None] = mapped_column(String(500))
    deleted_profiles: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class FaceEnrollmentRequest(UUIDPrimaryKeyMixin, Base):
    """Idempotency record for POST /face/enroll: a retried request replays the first result."""
    __tablename__ = "face_enrollment_requests"

    request_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # Erasing the Face ID nulls this, so the old request can no longer be replayed as a success.
    face_profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("face_profiles.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Device(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("api_key_hash", name="uq_devices_api_key_hash"),)

    device_code: Mapped[str] = mapped_column(String(80), unique=True)
    device_name: Mapped[str] = mapped_column(String(150))
    location: Mapped[str | None] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    # SHA-256 of a high-entropy device key; the raw key is shown to staff once.
    api_key_hash: Mapped[str | None] = mapped_column(String(64))
    api_key_prefix: Mapped[str | None] = mapped_column(String(16))
    api_key_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_sessions"
    __table_args__ = (
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at"),
        CheckConstraint("duration_seconds IS NULL OR duration_seconds >= 0"),
        Index("ix_user_sessions_device_started", "device_id", "started_at"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("devices.id", ondelete="SET NULL"), index=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    identified: Mapped[bool] = mapped_column(Boolean, default=False)
    exit_reason: Mapped[str | None] = mapped_column(String(40))

    user: Mapped[User | None] = relationship(back_populates="sessions")
    face_logs: Mapped[list[FaceAuthenticationLog]] = relationship(back_populates="session")
    conversations: Mapped[list[Conversation]] = relationship(back_populates="session")


class FaceAuthenticationLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "face_authentication_logs"
    __table_args__ = (
        CheckConstraint("attempt_number > 0"),
        CheckConstraint("processing_time_ms IS NULL OR processing_time_ms >= 0"),
        CheckConstraint("confidence_score IS NULL OR confidence_score BETWEEN 0 AND 1"),
        Index("ix_face_auth_session_time", "session_id", "occurred_at"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_sessions.id", ondelete="SET NULL"), index=True
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("devices.id", ondelete="SET NULL"), index=True
    )
    result: Mapped[str] = mapped_column(String(40), index=True)
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    processing_time_ms: Mapped[int | None] = mapped_column(Integer)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    failure_reason: Mapped[str | None] = mapped_column(String(255))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    session: Mapped[UserSession | None] = relationship(back_populates="face_logs")


class InteractionEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "interaction_events"
    __table_args__ = (
        Index("ix_interaction_session_time", "session_id", "event_time"),
        Index("ix_interaction_type_time", "event_type", "event_time"),
    )

    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_sessions.id", ondelete="SET NULL"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("devices.id", ondelete="SET NULL"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    input_method: Mapped[str | None] = mapped_column(String(30))
    content_summary: Mapped[str | None] = mapped_column(Text)
    success: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class KnowledgeSource(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "knowledge_sources"
    __table_args__ = (
        CheckConstraint("file_size IS NULL OR file_size >= 0"),
    )

    source_name: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(40), index=True)
    original_file_name: Mapped[str | None] = mapped_column(String(500))
    file_mime_type: Mapped[str | None] = mapped_column(String(150))
    file_size: Mapped[int | None] = mapped_column(Integer)
    source_url: Mapped[str | None] = mapped_column(Text)
    storage_path: Mapped[str | None] = mapped_column(Text)
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(String(40), index=True)
    processing_error: Mapped[str | None] = mapped_column(Text)

    documents: Mapped[list[KnowledgeDocument]] = relationship(back_populates="source")


class KnowledgeDocument(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "knowledge_documents"

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_sources.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(500))
    document_type: Mapped[str | None] = mapped_column(String(80))
    language: Mapped[str | None] = mapped_column(String(10))
    version: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(40), index=True)

    source: Mapped[KnowledgeSource] = relationship(back_populates="documents")
    chunks: Mapped[list[KnowledgeChunk]] = relationship(back_populates="document")


class KnowledgeChunk(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index"),
        CheckConstraint("chunk_index >= 0"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="RESTRICT"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    chunk_text: Mapped[str] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer)
    sheet_name: Mapped[str | None] = mapped_column(String(255))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (CheckConstraint("ended_at IS NULL OR ended_at >= started_at"),)

    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_sessions.id", ondelete="SET NULL"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), index=True)

    session: Mapped[UserSession | None] = relationship(back_populates="conversations")
    messages: Mapped[list[ConversationMessage]] = relationship(back_populates="conversation")


class ConversationMessage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (Index("ix_message_conversation_time", "conversation_id", "message_time"),)

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="RESTRICT"), index=True
    )
    sender_type: Mapped[str] = mapped_column(String(20), index=True)
    message_text: Mapped[str | None] = mapped_column(Text)
    input_method: Mapped[str | None] = mapped_column(String(30))
    message_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    intent_detected: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class PromptVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (
        UniqueConstraint("prompt_name", "version_number"),
        CheckConstraint("version_number > 0"),
    )

    prompt_name: Mapped[str] = mapped_column(String(150), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    prompt_text: Mapped[str] = mapped_column(Text)
    change_reason: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AIRequest(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ai_requests"
    __table_args__ = (
        CheckConstraint("input_token_count IS NULL OR input_token_count >= 0"),
        CheckConstraint("output_token_count IS NULL OR output_token_count >= 0"),
        CheckConstraint("latency_ms IS NULL OR latency_ms >= 0"),
        Index("ix_ai_request_conversation_created", "conversation_id", "created_at"),
    )

    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), index=True
    )
    user_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversation_messages.id", ondelete="SET NULL")
    )
    request_type: Mapped[str] = mapped_column(String(40), index=True)
    model_name: Mapped[str | None] = mapped_column(String(120))
    prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("prompt_versions.id", ondelete="SET NULL")
    )
    input_token_count: Mapped[int | None] = mapped_column(Integer)
    output_token_count: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    responses: Mapped[list[AIResponse]] = relationship(back_populates="request")


class AIResponse(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ai_responses"
    __table_args__ = (
        CheckConstraint("confidence_score IS NULL OR confidence_score BETWEEN 0 AND 1"),
    )

    ai_request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_requests.id", ondelete="RESTRICT"), index=True
    )
    ai_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversation_messages.id", ondelete="SET NULL")
    )
    response_text: Mapped[str | None] = mapped_column(Text)
    response_summary: Mapped[str | None] = mapped_column(Text)
    grounded: Mapped[bool | None] = mapped_column(Boolean)
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    # Knowledge chunks the answer was grounded on: [{chunk_id, document_id, title, page_number, sheet_name}].
    citations: Mapped[list[dict[str, Any]] | None] = mapped_column(PortableJSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    request: Mapped[AIRequest] = relationship(back_populates="responses")
    feedback: Mapped[list[AIFeedback]] = relationship(back_populates="response")


class AIFeedback(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ai_feedback"
    __table_args__ = (
        CheckConstraint("rating_score IS NULL OR rating_score BETWEEN 1 AND 5"),
    )

    ai_response_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_responses.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    rating_score: Mapped[int | None] = mapped_column(Integer)
    is_helpful: Mapped[bool | None] = mapped_column(Boolean)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    response: Mapped[AIResponse] = relationship(back_populates="feedback")


class BookCategory(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "book_categories"

    category_name: Mapped[str] = mapped_column(String(150), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    books: Mapped[list[SuggestedBook]] = relationship(back_populates="category")


class SuggestedBook(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "suggested_books"

    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("book_categories.id", ondelete="SET NULL"), index=True
    )
    external_book_id: Mapped[str | None] = mapped_column(String(120), index=True)
    title: Mapped[str] = mapped_column(String(500), index=True)
    author_name: Mapped[str | None] = mapped_column(String(255))
    short_description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(255))

    category: Mapped[BookCategory | None] = relationship(back_populates="books")


class BookSuggestionLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "book_suggestion_logs"
    __table_args__ = (
        CheckConstraint("feedback_score IS NULL OR feedback_score BETWEEN 1 AND 5"),
        Index("ix_book_suggestion_session_shown", "session_id", "shown_at"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_sessions.id", ondelete="SET NULL"), index=True
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("book_categories.id", ondelete="SET NULL")
    )
    suggested_book_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("suggested_books.id", ondelete="SET NULL")
    )
    shown_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    clicked: Mapped[bool | None] = mapped_column(Boolean)
    feedback_score: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Survey(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "surveys"
    __table_args__ = (
        UniqueConstraint("survey_name", "version"),
        CheckConstraint("version > 0"),
    )

    survey_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    questions: Mapped[list[SurveyQuestion]] = relationship(back_populates="survey")
    responses: Mapped[list[SurveyResponse]] = relationship(back_populates="survey")


class SurveyQuestion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "survey_questions"
    __table_args__ = (
        UniqueConstraint("survey_id", "question_order"),
        CheckConstraint("question_order > 0"),
    )

    survey_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("surveys.id", ondelete="RESTRICT"), index=True
    )
    question_text: Mapped[str] = mapped_column(Text)
    question_type: Mapped[str] = mapped_column(String(30))
    question_order: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    survey: Mapped[Survey] = relationship(back_populates="questions")
    answers: Mapped[list[SurveyAnswer]] = relationship(back_populates="question")


class SurveyResponse(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "survey_responses"
    __table_args__ = (Index("ix_survey_response_session_time", "session_id", "submitted_at"),)

    survey_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("surveys.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_sessions.id", ondelete="SET NULL"), index=True
    )
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    survey: Mapped[Survey] = relationship(back_populates="responses")
    answers: Mapped[list[SurveyAnswer]] = relationship(back_populates="response")


class SurveyAnswer(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "survey_answers"
    __table_args__ = (UniqueConstraint("response_id", "question_id"),)

    response_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("survey_responses.id", ondelete="RESTRICT"), index=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("survey_questions.id", ondelete="RESTRICT"), index=True
    )
    answer_text: Mapped[str | None] = mapped_column(Text)
    answer_number: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    response: Mapped[SurveyResponse] = relationship(back_populates="answers")
    question: Mapped[SurveyQuestion] = relationship(back_populates="answers")


class DailyReportMetric(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "daily_report_metrics"
    __table_args__ = (
        CheckConstraint(
            "total_sessions >= 0 AND total_identified_users >= 0 "
            "AND total_questions >= 0 AND total_ai_answers >= 0 AND total_surveys >= 0"
        ),
        CheckConstraint(
            "avg_satisfaction_score IS NULL OR avg_satisfaction_score BETWEEN 1 AND 5"
        ),
        CheckConstraint(
            "avg_ai_response_time_ms IS NULL OR avg_ai_response_time_ms >= 0"
        ),
    )

    report_date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    total_sessions: Mapped[int] = mapped_column(Integer, default=0)
    total_identified_users: Mapped[int] = mapped_column(Integer, default=0)
    total_questions: Mapped[int] = mapped_column(Integer, default=0)
    total_ai_answers: Mapped[int] = mapped_column(Integer, default=0)
    total_surveys: Mapped[int] = mapped_column(Integer, default=0)
    avg_satisfaction_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    avg_ai_response_time_ms: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))


class Department(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "departments"
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)  # e.g. 'CNTT', 'NN'
    name: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    majors: Mapped[list[Major]] = relationship(back_populates="department")


class Major(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "majors"
    department_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("departments.id", ondelete="RESTRICT"), index=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)  # e.g. 'CNTT-KTPM'
    name: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    department: Mapped[Department] = relationship(back_populates="majors")


class ChatSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "chat_sessions"
    kiosk_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"), index=True)
    major_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("majors.id", ondelete="SET NULL"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    messages: Mapped[list[ChatMessage]] = relationship(back_populates="session")


class ChatMessage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint("feedback_score IS NULL OR feedback_score IN (-1, 1)"),
        CheckConstraint("latency_ms IS NULL OR latency_ms >= 0"),
        Index("ix_chat_message_session_time", "session_id", "created_at"),
    )
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_sessions.id", ondelete="RESTRICT"), index=True)
    role: Mapped[str] = mapped_column(String(20), index=True)  # 'user', 'assistant', 'system'
    content: Mapped[str] = mapped_column(Text)
    intent_detected: Mapped[str | None] = mapped_column(String(120))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    feedback_score: Mapped[int | None] = mapped_column(Integer)  # -1 dislike, 1 like
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    session: Mapped[ChatSession] = relationship(back_populates="messages")


class StaffAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Library staff who sign in to the admin UI. Not a kiosk visitor (`users`)."""
    __tablename__ = "staff_accounts"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'librarian')"),
        CheckConstraint("failed_login_count >= 0"),
    )

    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sessions: Mapped[list[StaffSession]] = relationship(back_populates="staff")


class StaffSession(UUIDPrimaryKeyMixin, Base):
    """Revocable admin session; only a SHA-256 digest of the bearer token is stored."""
    __tablename__ = "staff_sessions"
    __table_args__ = (CheckConstraint("expires_at > created_at"),)

    staff_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("staff_accounts.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    binding_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    staff: Mapped[StaffAccount] = relationship(back_populates="sessions")
