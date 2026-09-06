from uuid import uuid4
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.api.v1.routes import runtime
from app.services.realtime_face_service import RealtimeFaceService, Track, overlap
from app.vision.engine import VisionEngine
from app.vision.presence_detector import PresenceDetector
from app.vision.recognition_service import RecognitionService
from app.vision.session_controller import SessionController


def test_tracking_retains_id_and_clears_votes_after_loss():
    service = RealtimeFaceService()
    track = service.track([(10, 150, 150, 10)], 10)[0]
    assert not track.vote("a")
    assert service.track([(11, 151, 151, 11)], 10.2)[0].id == track.id
    assert not track.vote("a")
    service.track([], 10.3)
    assert track.votes == 0
    assert service.track([(11, 151, 151, 11)], 12)[0].id == track.id
    for frame in range(6):
        service.track([], 13 + frame)
    assert service.track([(11, 151, 151, 11)], 20)[0].id != track.id


def test_tracking_is_not_expired_by_slow_frame_processing():
    service = RealtimeFaceService()
    first = service.track([(10, 150, 150, 10)], 1)[0]
    second = service.track([(14, 154, 154, 14)], 4.5)[0]
    assert second.id == first.id
    assert second.hits == 2


def test_identity_must_match_three_consecutive_observations():
    track = Track(1, (0, 100, 100, 0), 0, 0)
    assert not track.vote("a")
    assert not track.vote("b")
    assert not track.vote("b")
    assert track.vote("b")
    assert not track.vote(None)
    assert not track.vote("b")


def test_recognition_cadence_is_exactly_half_a_second():
    track = Track(1, (0, 100, 100, 0), 0, 0, last_recognition=10)
    service = RecognitionService()
    assert not service.should_recognize(track, 10.499)
    assert service.should_recognize(track, 10.5)


def test_presence_and_session_controllers_reset_connection_evidence():
    presence = PresenceDetector(1.2)
    assert presence.update(True, 10) == (False, False)
    assert presence.update(True, 11.21) == (True, False)
    assert presence.update(False, 11.3) == (False, True)
    controller = SessionController()
    controller.configure("recognition", "session-1")
    candidate = object()
    controller.offer(candidate)
    assert controller.accept("other-session") is None
    assert controller.accept("session-1") is candidate


def test_crossing_and_multiple_faces_do_not_share_tracks():
    service = RealtimeFaceService()
    tracks = service.track([(0, 100, 100, 0), (0, 300, 100, 200)], 0)
    assert len({t.id for t in tracks}) == 2
    assert overlap(tracks[0].box, tracks[1].box) == 0
    moved = service.track([(0, 101, 100, 1), (0, 299, 100, 199)], .2)
    assert [t.id for t in tracks] == [t.id for t in moved]


def test_stream_rejects_foreign_origin():
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/api/v1/kiosk/stream", headers={"origin": "https://foreign.example"}):
                pass


def read_until(socket, event):
    events = []
    for _ in range(20):
        message = socket.receive_json()
        events.append(message)
        if message["event"] == event:
            return events
    raise AssertionError(f"Missing {event}")


def test_confirmation_requires_three_frames_and_client_acceptance(monkeypatch):
    ticks = iter(range(100, 1000))
    monkeypatch.setattr(runtime, "monotonic", lambda: next(ticks))
    def inspect(self, data):
        if 1 not in self.tracks:
            self.tracks[1] = Track(1, (0, 100, 100, 0), 0, 0)
        return None, [{"track_id": 1, "quality_ok": True, "box": [0, 100, 100, 0], "guidance": None}]
    monkeypatch.setattr(VisionEngine, "inspect", inspect)
    result = SimpleNamespace(result="SUCCESS", user_id=uuid4(), confidence_score=.93)
    monkeypatch.setattr(runtime, "load_candidates", lambda: [])
    monkeypatch.setattr(RecognitionService, "recognize", lambda self, image, box, candidates: result)
    confirmations = []
    monkeypatch.setattr(runtime, "confirm", lambda session, match: confirmations.append(session) or {"user": {"id": str(match.user_id)}})
    with TestClient(app) as client, client.websocket_connect("/api/v1/kiosk/stream", headers={"origin": "http://localhost:5173"}) as socket:
        assert socket.receive_json()["event"] == "stream_ready"
        socket.send_json({"event": "CONFIGURE", "payload": {"mode": "recognition", "session_id": "test"}})
        read_until(socket, "session_state")
        for index in range(3):
            socket.send_bytes(b"frame")
            events = read_until(socket, "frame_ready")
            assert any(e["event"] == "identity_candidate" and e["payload"].get("confirmed") for e in events) == (index == 2)
            assert not confirmations
        socket.send_json({"event": "confirm_identity", "payload": {"session_id": "test"}})
        read_until(socket, "identity_confirmed")
        assert confirmations == ["test"]
        socket.send_bytes(b"late frame")
        assert [e["event"] for e in read_until(socket, "frame_ready")] == ["frame_ready"]


def test_stream_recovers_from_invalid_frame_without_committing(monkeypatch):
    def invalid(self, data):
        raise ValueError("bad jpeg")
    monkeypatch.setattr(VisionEngine, "inspect", invalid)
    with TestClient(app) as client, client.websocket_connect("/api/v1/kiosk/stream", headers={"origin": "http://localhost:5173"}) as socket:
        socket.receive_json()
        socket.send_bytes(b"not jpeg")
        events = read_until(socket, "frame_ready")
        assert [event["event"] for event in events] == ["stream_error", "frame_ready"]
        socket.send_json({"event": "PING", "payload": {"sent_at": 42}})
        assert socket.receive_json()["payload"]["sent_at"] == 42
