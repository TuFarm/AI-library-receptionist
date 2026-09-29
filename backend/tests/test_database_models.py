from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import configure_mappers
from sqlalchemy.schema import CreateTable

from app import models  # noqa: F401
from app.core.database import Base
from app.services.user_service import calculate_student_year


EXPECTED_TABLES = {
    "users", "user_preferences", "face_profiles", "face_authentication_logs",
    "devices", "user_sessions", "interaction_events", "knowledge_sources",
    "knowledge_documents", "knowledge_chunks", "conversations",
    "conversation_messages", "ai_requests", "ai_responses", "ai_feedback",
    "prompt_versions", "book_categories", "suggested_books",
    "book_suggestion_logs", "surveys", "survey_questions", "survey_responses",
    "survey_answers", "daily_report_metrics",
    "departments", "majors", "chat_sessions", "chat_messages",
    "staff_accounts", "staff_sessions",
}

OLD_TABLES = {
    "authors", "publishers", "books", "book_copies", "shelves",
    "borrowing_records", "return_events", "ebooks", "recommendation_runs",
    "recommendation_items", "research_studies", "experiment_groups",
    "participant_assignments", "dim_date", "fact_borrowing", "ml_datasets",
}


def test_metadata_loads_and_compiles_for_postgresql():
    configure_mappers()
    assert set(Base.metadata.tables) == EXPECTED_TABLES
    for table in Base.metadata.sorted_tables:
        str(CreateTable(table).compile(dialect=postgresql.dialect()))


def test_old_full_library_tables_are_absent():
    assert OLD_TABLES.isdisjoint(Base.metadata.tables)


def test_user_fields_uniqueness_and_student_columns():
    users = Base.metadata.tables["users"]
    assert users.c.student_code.unique
    assert users.c.email.unique
    assert {"faculty", "major", "admission_year"} <= set(users.c.keys())
    assert "student_year" not in users.c


def test_calculate_student_year():
    assert calculate_student_year(None, 2026) is None
    assert calculate_student_year(2023, 2026) == 4
    assert calculate_student_year(2026, 2026) == 1
    assert calculate_student_year(2027, 2026) is None


def test_nullable_identity_for_unknown_face_and_anonymous_session():
    assert Base.metadata.tables["face_authentication_logs"].c.user_id.nullable
    assert Base.metadata.tables["user_sessions"].c.user_id.nullable


def test_required_constraints_are_declared():
    constrained = (
        "users", "face_authentication_logs", "knowledge_chunks", "ai_requests",
        "ai_responses", "ai_feedback", "prompt_versions", "book_suggestion_logs",
        "survey_questions", "daily_report_metrics",
    )
    for name in constrained:
        assert any(
            isinstance(constraint, CheckConstraint)
            for constraint in Base.metadata.tables[name].constraints
        ), name
    assert any(
        isinstance(constraint, UniqueConstraint)
        for constraint in Base.metadata.tables["knowledge_chunks"].constraints
    )


def test_knowledge_relationship_chain():
    assert Base.metadata.tables["knowledge_documents"].c.source_id.foreign_keys
    assert Base.metadata.tables["knowledge_chunks"].c.document_id.foreign_keys


def test_conversation_ai_feedback_relationship_chain():
    assert Base.metadata.tables["conversation_messages"].c.conversation_id.foreign_keys
    assert Base.metadata.tables["ai_requests"].c.conversation_id.foreign_keys
    assert Base.metadata.tables["ai_responses"].c.ai_request_id.foreign_keys
    assert Base.metadata.tables["ai_feedback"].c.ai_response_id.foreign_keys


def test_survey_relationship_chain():
    assert Base.metadata.tables["survey_questions"].c.survey_id.foreign_keys
    assert Base.metadata.tables["survey_responses"].c.survey_id.foreign_keys
    assert Base.metadata.tables["survey_answers"].c.response_id.foreign_keys
    assert Base.metadata.tables["survey_answers"].c.question_id.foreign_keys


def test_simple_book_suggestion_history_relationships():
    assert Base.metadata.tables["suggested_books"].c.category_id.foreign_keys
    log = Base.metadata.tables["book_suggestion_logs"]
    assert log.c.category_id.foreign_keys
    assert log.c.suggested_book_id.foreign_keys
    assert log.c.user_id.nullable and log.c.session_id.nullable


def test_daily_report_metric_grain():
    table = Base.metadata.tables["daily_report_metrics"]
    assert table.c.report_date.unique
    assert {"total_sessions", "total_questions", "total_ai_answers"} <= set(table.c.keys())


def test_append_only_tables_have_no_soft_delete_column():
    append_only = {
        "face_authentication_logs", "interaction_events", "ai_requests",
        "ai_responses", "ai_feedback", "book_suggestion_logs",
        "survey_responses", "survey_answers", "daily_report_metrics",
    }
    for name in append_only:
        assert "deleted_at" not in Base.metadata.tables[name].c
