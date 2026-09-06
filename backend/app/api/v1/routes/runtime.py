"""Bounded duplex kiosk stream. Business transactions reuse existing services."""
import asyncio
import json
import logging
from datetime import UTC, datetime
from decimal import Decimal
from time import monotonic
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.api.v1.routes.ai import runtime_answer
from app.api.v1.routes.face import _user_data
from app.api.v1.routes.voice import browser_transcript
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.schema import Conversation, FaceAuthenticationLog, FaceProfile, User, UserSession
from app.schemas.ai import AIRuntimeRequest
from app.schemas.voice import BrowserTranscriptCreate
from app.services.face_service import FaceProviderUnavailable
from app.services.interaction_service import record_event
from app.vision.engine import VisionEngine
from app.vision.event_publisher import EventPublisher
from app.vision.presence_detector import PresenceDetector
from app.vision.recognition_service import RecognitionService
from app.vision.session_controller import SessionController

router = APIRouter()
logger = logging.getLogger(__name__)


def load_candidates():
    if settings.face_provider != "local":
        raise FaceProviderUnavailable("Realtime identity confirmation requires FACE_PROVIDER=local; mock identity is disabled on the stream")
    with SessionLocal() as db:
        profiles = db.scalars(select(FaceProfile).join(User).where(
            FaceProfile.active.is_(True), FaceProfile.deleted_at.is_(None), User.deleted_at.is_(None))).all()
        return [(p.user_id, p.face_template_encrypted, p.face_template_ref) for p in profiles]


def confirm(session_id, result):
    with SessionLocal() as db:
        session = db.get(UserSession, UUID(session_id))
        user = db.get(User, result.user_id)
        if not session or session.ended_at is not None or not user or user.deleted_at is not None:
            raise ValueError("Session or identity unavailable")
        session.user_id, session.identified = user.id, True
        db.add(FaceAuthenticationLog(user_id=user.id, session_id=session.id, device_id=session.device_id,
            result="SUCCESS", confidence_score=Decimal(str(result.confidence_score)), attempt_number=1,
            occurred_at=datetime.now(UTC)))
        record_event(db, event_type="FACE_RECOGNIZED", session_id=session.id, user_id=user.id,
                     device_id=session.device_id, success=True)
        payload = {"result": "SUCCESS", "user": _user_data(user), "confidence_score": result.confidence_score, "next_state": "WELCOME"}
        db.commit()
        return payload


def answer(payload):
    with SessionLocal() as db:
        request = AIRuntimeRequest(**payload)
        session = db.get(UserSession, request.session_id)
        conversation = db.get(Conversation, request.conversation_id)
        if not session or session.ended_at is not None or not conversation or conversation.session_id != session.id:
            raise ValueError("Conversation does not belong to active session")
        if payload.get("input_method") == "VOICE":
            browser_transcript(BrowserTranscriptCreate(session_id=request.session_id, conversation_id=request.conversation_id,
                transcript=request.message_text, confidence_score=payload.get("confidence_score")), db)
            request.save_user_message = False
        else:
            request.save_user_message = True
        return runtime_answer(request, db)["data"]


@router.websocket("/stream")
async def stream(socket: WebSocket):
    origin = socket.headers.get("origin", "")
    if origin not in settings.kiosk_stream_origins.split(","):
        await socket.close(code=1008)
        return
    await socket.accept()
    vision = VisionEngine()
    presence = PresenceDetector()
    controller = SessionController()
    recognition = RecognitionService()
    last_frame = 0.0
    completed_requests = {}
    candidates = None
    publisher = EventPublisher(socket)

    await publisher.publish("stream_ready")
    try:
        while True:
            message = await asyncio.wait_for(socket.receive(), timeout=90)
            if message["type"] == "websocket.disconnect":
                break
            data = message.get("bytes")
            if data is not None:
                started = monotonic()
                try:
                    if len(data) > 2_500_000:
                        raise ValueError("Frame exceeds 2.5 MB")
                    if controller.locked or started-last_frame < (.7 if controller.mode == "idle" else .025):
                        continue
                    last_frame = started
                    image, detections = await run_in_threadpool(vision.inspect, data)
                    frame_size = [int(image.shape[1]), int(image.shape[0])] if image is not None else [1920, 1080]
                    await publisher.publish("face_tracking", {"faces": detections, "frame_size": frame_size,
                                                               "metrics": vision.metrics})
                    for lifecycle in vision.tracker.last_events:
                        await publisher.publish(lifecycle["event"], {key: value for key, value in lifecycle.items() if key != "event"})
                    if not detections:
                        _, lost = presence.update(False, started)
                        if lost:
                            await publisher.publish("presence_lost")
                    else:
                        await publisher.publish("face_detected", {"track_ids": [face["track_id"] for face in detections]})
                        confirmed_presence, _ = presence.update(True, started)
                        if controller.mode == "idle" and confirmed_presence:
                            await publisher.publish("presence_detected")
                        if controller.mode in {"recognition", "registration"}:
                            for detection in detections:
                                track = vision.tracks[detection["track_id"]]
                                if not detection["quality_ok"]:
                                    await publisher.publish("face_quality_bad", detection)
                                    continue
                                await publisher.publish("face_quality_good", detection)
                                recognition_now = monotonic()
                                if controller.mode == "registration" or not recognition.should_recognize(track, recognition_now):
                                    continue
                                track.last_recognition = recognition_now
                                await publisher.publish("recognition_started", {"track_id": track.id})
                                attempt_started = monotonic()
                                try:
                                    if candidates is None:
                                        candidates = await run_in_threadpool(load_candidates)
                                    result = await run_in_threadpool(
                                        recognition.recognize, image, tuple(detection["box"]), candidates
                                    )
                                except Exception:
                                    await publisher.publish("recognition_finished", {
                                        "track_id": track.id, "result": "ERROR",
                                        "recognition_ms": round((monotonic() - attempt_started) * 1000, 1),
                                    })
                                    raise
                                candidate = str(result.user_id) if result.result == "SUCCESS" else None
                                progress = {"track_id": track.id, "confidence": result.confidence_score,
                                            "result": result.result, **recognition.metrics}
                                await publisher.publish("recognition_progress", progress)
                                await publisher.publish("recognition_finished", progress)
                                if candidate:
                                    await publisher.publish("identity_candidate", {"track_id": track.id, "confidence": result.confidence_score, "votes": track.votes + 1})
                                else:
                                    await publisher.publish("identity_unknown", {"track_id": track.id, "confidence": result.confidence_score})
                                if track.vote(candidate) and controller.session_id:
                                    controller.offer(result)
                                    await publisher.publish("identity_candidate", {"track_id": track.id, "session_id": controller.session_id, "confidence": result.confidence_score, "votes": track.votes, "confirmed": True})
                except Exception:
                    logger.exception("Kiosk frame processing failed")
                    for track in vision.tracks.values():
                        track.reset()
                    await publisher.publish("stream_error", {"message": "Nhận diện chưa sẵn sàng. Vui lòng kiểm tra camera và bộ nhận diện."})
                finally:
                    await publisher.publish("frame_ready", {"latency_ms": round((monotonic()-started)*1000)})
                continue
            text = message.get("text", "")
            if len(text) > 32_000:
                await socket.close(code=1009)
                break
            command = json.loads(text)
            kind, payload = command.get("event"), command.get("payload", {})
            request_id = command.get("request_id")
            if kind == "CONFIGURE":
                next_mode = payload.get("mode", "idle")
                controller.configure(next_mode, payload.get("session_id"))
                vision = VisionEngine()
                recognition = RecognitionService()
                candidates = None
                presence.reset()
                await publisher.publish("session_state", {"mode": controller.mode, "session_id": controller.session_id})
            elif kind == "confirm_identity":
                proposal = controller.accept(payload.get("session_id"))
                if proposal:
                    result = await run_in_threadpool(confirm, controller.session_id, proposal)
                    await publisher.publish("identity_confirmed", result)
            elif kind == "AI_REQUEST":
                try:
                    if not isinstance(request_id, str) or len(request_id) > 100:
                        raise ValueError("Request ID required")
                    if request_id in completed_requests:
                        await publisher.publish("ai_processing_finished", completed_requests[request_id], request_id)
                        continue
                    if not controller.session_id or payload.get("session_id") != controller.session_id:
                        raise ValueError("Session mismatch")
                    await publisher.publish("ai_processing_started", request_id=request_id)
                    result = await run_in_threadpool(answer, payload)
                    completed_requests[request_id] = result
                    if len(completed_requests) > 32:
                        del completed_requests[next(iter(completed_requests))]
                    await publisher.publish("ai_processing_finished", result, request_id)
                except Exception:
                    logger.exception("Kiosk AI turn failed")
                    await publisher.publish("request_error", {"message": "Không thể xử lý câu hỏi."}, request_id)
            elif kind == "PING":
                await publisher.publish("pong", payload)
            elif kind in {"camera_ready", "registration_requested", "voice_ready", "transcript_updated", "ai_listening_started", "ai_listening_stopped", "ai_speaking_started", "ai_speaking_finished", "survey_started", "survey_completed", "session_reset"}:
                await publisher.publish(kind, payload)
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    except Exception:
        logger.exception("Kiosk stream closed after invalid command")
        await socket.close(code=1008)
