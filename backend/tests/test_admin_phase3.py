"""Survey management, conversation logs and the daily report job on an isolated SQL database."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.schema import (
    AIRequest, AIResponse, Conversation, ConversationMessage, DailyReportMetric, Device, InteractionEvent,
    SurveyResponse, User, UserSession,
)
from app.services import report_service
from tests.conftest import TEST_DEVICE_ID

SURVEYS = "/api/v1/admin/surveys"
CONVERSATIONS = "/api/v1/admin/conversations"
SURVEY = {"survey_name": "Khảo sát trải nghiệm", "description": "Sau mỗi phiên",
          "questions": [{"question_text": "Bạn hài lòng không?", "question_type": "rating"},
                        {"question_text": "AI có giúp bạn không?", "question_type": "yes_no"},
                        {"question_text": "Góp ý thêm?", "question_type": "text"}]}


@pytest.fixture
def staff(use_db, admin_staff):
    return TestClient(app)


def test_admin_routes_require_staff(use_db):
    client = TestClient(app)
    for method, url in (("GET", SURVEYS), ("POST", SURVEYS), ("GET", CONVERSATIONS),
                        ("POST", "/api/v1/reports/daily/rebuild")):
        assert client.request(method, url, json={}).status_code == 401, url


# --- surveys ------------------------------------------------------------------------------------

def create(staff, **changes):
    response = staff.post(SURVEYS, json={**SURVEY, **changes})
    assert response.status_code == 201, response.json()
    return response.json()["data"]


def test_survey_lifecycle_and_single_active_survey(staff):
    first = create(staff)
    assert first["active"] is False and first["version"] == 1 and len(first["questions"]) == 3
    assert staff.get("/api/v1/surveys/active").json()["data"] is None  # nothing shown until activated

    staff.post(f"{SURVEYS}/{first['id']}/activate")
    active = staff.get("/api/v1/surveys/active").json()["data"]
    assert active["id"] == first["id"] and [q["type"] for q in active["questions"]] == ["rating", "yes_no", "text"]

    second = create(staff)
    assert second["version"] == 2
    staff.post(f"{SURVEYS}/{second['id']}/activate")
    listed = {item["id"]: item["active"] for item in staff.get(SURVEYS).json()["data"]}
    assert listed == {first["id"]: False, second["id"]: True}

    edited = staff.patch(f"{SURVEYS}/{second['id']}", json={"description": None, "questions": SURVEY["questions"][:1]}).json()["data"]
    assert edited["description"] is None and len(edited["questions"]) == 1
    assert staff.delete(f"{SURVEYS}/{second['id']}").status_code == 200
    assert staff.get(f"{SURVEYS}/{second['id']}").status_code == 404
    assert staff.get("/api/v1/surveys/active").json()["data"] is None


@pytest.mark.parametrize("payload", [
    {**SURVEY, "questions": []},
    {**SURVEY, "questions": [{"question_text": "Chọn?", "question_type": "multiple_choice"}]},
    {**SURVEY, "survey_name": "  "},
    {**SURVEY, "unknown": 1},
])
def test_survey_validation(staff, payload):
    assert staff.post(SURVEYS, json=payload).status_code == 422


def test_kiosk_answers_are_validated_and_questions_freeze_after_responses(staff):
    survey = create(staff)
    staff.post(f"{SURVEYS}/{survey['id']}/activate")
    rating, yes_no, text = (q["id"] for q in survey["questions"])
    submit = lambda answers: staff.post(f"/api/v1/surveys/{survey['id']}/responses", json={"answers": answers})  # noqa: E731
    for bad in ({rating: 6}, {rating: 4.5}, {rating: True}, {yes_no: "Maybe"}, {text: "  "}, {text: "x" * 1001}):
        response = submit(bad)
        assert response.status_code == 422 and response.json()["error"]["code"] == "INVALID_SURVEY_ANSWER", bad
    assert submit({rating: 5, yes_no: "Có", text: "Rất tiện"}).status_code == 200
    assert submit({rating: 3, yes_no: "Không"}).status_code == 200

    locked = staff.patch(f"{SURVEYS}/{survey['id']}", json={"questions": SURVEY["questions"][:1]})
    assert locked.status_code == 409 and locked.json()["error"]["code"] == "SURVEY_HAS_RESPONSES"
    assert staff.patch(f"{SURVEYS}/{survey['id']}", json={"description": "Mới"}).status_code == 200

    results = staff.get(f"{SURVEYS}/{survey['id']}/results").json()["data"]
    assert results["response_count"] == 2
    by_type = {q["type"]: q for q in results["questions"]}
    assert by_type["rating"]["average"] == 4 and by_type["rating"]["distribution"]["5"] == 1
    assert by_type["yes_no"]["distribution"] == {"Có": 1, "Không": 1}
    assert by_type["text"]["recent_answers"][0]["text"] == "Rất tiện"

    copy = staff.post(f"{SURVEYS}/{survey['id']}/duplicate").json()["data"]
    assert copy["version"] == 2 and copy["response_count"] == 0 and copy["active"] is False
    assert staff.patch(f"{SURVEYS}/{copy['id']}", json={"questions": SURVEY["questions"][:2]}).status_code == 200


# --- conversations ------------------------------------------------------------------------------

def seed_conversation(db, *, text, grounded, minutes_ago=5, user=None):
    now = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    session = UserSession(device_id=TEST_DEVICE_ID, user_id=user.id if user else None, started_at=now, identified=bool(user))
    db.add(session); db.flush()
    conversation = Conversation(session_id=session.id, user_id=user.id if user else None, started_at=now, status="active")
    db.add(conversation); db.flush()
    question = ConversationMessage(conversation_id=conversation.id, sender_type="USER", message_text=text,
                                   input_method="VOICE", message_time=now)
    answer = ConversationMessage(conversation_id=conversation.id, sender_type="ASSISTANT", message_text="Trả lời",
                                 input_method="SYSTEM", message_time=now + timedelta(seconds=2))
    db.add_all([question, answer]); db.flush()
    request = AIRequest(conversation_id=conversation.id, user_message_id=question.id, request_type="library_qa",
                        model_name="bm25-extractive", latency_ms=120, status="completed")
    db.add(request); db.flush()
    citations = [{"index": 1, "chunk_id": "c", "document_id": "d", "title": "Nội quy", "page_number": None, "sheet_name": None}]
    db.add(AIResponse(ai_request_id=request.id, ai_message_id=answer.id, response_text="Trả lời", grounded=grounded,
                      citations=citations if grounded else None))
    db.commit()
    return conversation


def test_conversation_logs_list_filter_and_detail(staff, use_db):
    db = use_db
    db.add(Device(id=TEST_DEVICE_ID, device_code="KIOSK_TEST", device_name="Sảnh", status="active")); db.flush()
    student = User(student_code="SV001", full_name="Nguyễn Văn A", email="a@example.test", user_type="student", account_status="active")
    db.add(student); db.flush()
    grounded = seed_conversation(db, text="Thư viện mở cửa mấy giờ?", grounded=True, user=student)
    missing = seed_conversation(db, text="Mật khẩu WiFi là gì?", grounded=False, minutes_ago=1)
    seed_conversation(db, text="Câu hỏi cũ", grounded=True, minutes_ago=60 * 24 * 10)

    listing = staff.get(CONVERSATIONS, params={"days": 7}).json()["data"]
    assert listing["total"] == 2 and listing["items"][0]["id"] == str(missing.id)
    first = listing["items"][1]
    assert first["visitor"]["student_code"] == "SV001" and first["device_code"] == "KIOSK_TEST"
    assert first["first_question"] == "Thư viện mở cửa mấy giờ?" and first["message_count"] == 2
    assert (first["answer_count"], first["grounded_count"]) == (1, 1)

    gaps = staff.get(CONVERSATIONS, params={"ungrounded": True}).json()["data"]
    assert [item["id"] for item in gaps["items"]] == [str(missing.id)]
    assert staff.get(CONVERSATIONS, params={"search": "wifi"}).json()["data"]["total"] == 1
    assert staff.get(CONVERSATIONS, params={"days": 30}).json()["data"]["total"] == 3

    detail = staff.get(f"{CONVERSATIONS}/{grounded.id}").json()["data"]
    assert [m["sender_type"] for m in detail["messages"]] == ["USER", "ASSISTANT"]
    assert detail["messages"][1]["ai"]["grounded"] is True and detail["messages"][1]["ai"]["citations"][0]["title"] == "Nội quy"
    assert staff.get(f"{CONVERSATIONS}/{TEST_DEVICE_ID}").status_code == 404


# --- daily report job ---------------------------------------------------------------------------

def test_daily_aggregation_is_idempotent_and_rebuild_endpoint(staff, use_db):
    db = use_db
    staff.post(SURVEYS, json=SURVEY)
    survey_id = staff.get(SURVEYS).json()["data"][0]["id"]
    staff.post(f"{SURVEYS}/{survey_id}/activate")
    rating = staff.get(f"{SURVEYS}/{survey_id}").json()["data"]["questions"][0]["id"]
    for score in (4, 5):
        staff.post(f"/api/v1/surveys/{survey_id}/responses", json={"answers": {rating: score}})
    now = datetime.now(UTC)
    db.add_all([UserSession(device_id=TEST_DEVICE_ID, started_at=now, identified=True),
                UserSession(device_id=TEST_DEVICE_ID, started_at=now, identified=False),
                UserSession(device_id=TEST_DEVICE_ID, started_at=now - timedelta(days=1), identified=False),
                InteractionEvent(event_type="QUESTION_ASKED", event_time=now),
                AIRequest(request_type="library_qa", latency_ms=100, status="completed"),
                AIRequest(request_type="library_qa", latency_ms=300, status="failed")])
    db.commit()

    today = now.date()
    for _ in range(2):
        row = report_service.aggregate_day(db, today); db.commit()
    assert db.query(DailyReportMetric).count() == 1
    assert (row.total_sessions, row.total_identified_users, row.total_questions, row.total_ai_answers, row.total_surveys) == (2, 1, 1, 1, 2)
    assert row.avg_satisfaction_score == Decimal("4.5") and row.avg_ai_response_time_ms == Decimal("200")

    rebuilt = staff.post("/api/v1/reports/daily/rebuild", params={"days": 3}).json()["data"]["metrics"]
    assert [m["total_sessions"] for m in rebuilt] == [0, 1, 2]
    daily = staff.get("/api/v1/reports/daily").json()["data"]["metrics"]
    assert daily[-1]["date"] == today.isoformat() and daily[-1]["avg_satisfaction_score"] == 4.5
    assert db.query(SurveyResponse).count() == 2  # raw facts untouched


def test_scheduler_records_success_and_survives_errors(monkeypatch, sqlite_db):
    import asyncio
    calls = []
    monkeypatch.setattr(report_service.settings, "report_job_interval_minutes", 5)

    async def stop_after_first_sleep(_):
        raise asyncio.CancelledError

    monkeypatch.setattr(report_service.asyncio, "sleep", stop_after_first_sleep)
    monkeypatch.setattr(report_service, "run_once", lambda factory: calls.append(factory))
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(report_service.report_scheduler("factory"))
    assert calls == ["factory"] and report_service.job_state.last_error is None

    def broken(_): raise RuntimeError("db down")
    monkeypatch.setattr(report_service, "run_once", broken)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(report_service.report_scheduler("factory"))
    assert report_service.job_state.last_error == "RuntimeError"
