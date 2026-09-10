from uuid import uuid4
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.api.v1.routes import runtime
from app.api.v1.routes.runtime import RegistrationStabilityGate
from app.services.face_service import ProviderFaceDetection
from app.services.realtime_face_service import RealtimeFaceService, Track, overlap
from app.vision.engine import VisionEngine
from app.vision.face_detector import DetectedFace
from app.vision.presence_detector import PresenceDetector
from app.vision.quality_estimator import QualityEstimator, QualityResult
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


def test_yunet_center_landmarks_pass_realtime_quality_without_dlib_eye_shape():
    image = (
        (np.indices((300, 300)).sum(axis=0) % 2)[:, :, None]
        * np.ones((1, 1, 3))
        * 200
    ).astype(np.uint8)
    provider_detection = ProviderFaceDetection(
        (30, 250, 250, 20),
        {
            "right_eye": [(75, 100)],
            "left_eye": [(165, 100)],
            "nose_tip": [(120, 145)],
            "top_lip": [(85, 205), (155, 205)],
        },
        (20.0, 30.0, 230.0, 220.0, 75.0, 100.0, 165.0, 100.0,
         120.0, 145.0, 85.0, 205.0, 155.0, 205.0, 0.98),
    )
    face = DetectedFace(
        provider_detection.box, provider_detection.quality_input, provider_detection
    )
    track = Track(1, face.box, 1.0, 0.5, hits=3)
    result = QualityEstimator().estimate(image, face, track, 1, 1.0)
    assert result.accepted is True


def test_vision_engine_keeps_provider_evidence_internal_to_current_frame():
    provider_detection = ProviderFaceDetection(
        (0, 200, 200, 0),
        {"left_eye": [(60, 70)], "right_eye": [(140, 70)], "nose_tip": [(100, 110)]},
        tuple(float(value) for value in range(15)),
    )

    class Decoder:
        def decode(self, _data):
            return np.zeros((200, 200, 3), dtype=np.uint8)

    class Detector:
        calls = 0

        def detect(self, _image):
            self.calls += 1
            return [DetectedFace(
                provider_detection.box,
                provider_detection.quality_input,
                provider_detection,
            )] if self.calls == 1 else []

    class Quality:
        def estimate(self, *_args):
            return QualityResult(True, None, 1.0, {})

    engine = VisionEngine(decoder=Decoder(), detector=Detector(), quality=Quality())
    _image, events = engine.inspect(b"frame-a")
    assert engine.provider_detection(events[0]["track_id"]) is provider_detection
    assert "provider_input" not in events[0]
    assert "embedding" not in events[0]
    engine.inspect(b"frame-b")
    assert engine.provider_detection(events[0]["track_id"]) is None


def test_registration_stability_resets_when_another_face_appears(monkeypatch):
    monkeypatch.setattr(runtime.settings, "registration_stable_frames", 3)
    monkeypatch.setattr(runtime.settings, "registration_stable_ms", 500)
    gate = RegistrationStabilityGate()
    assert not gate.observe(1, 1.0)
    assert not gate.observe(1, 1.3)
    gate.reset()  # zero/multiple faces invalidate all accumulated evidence
    assert not gate.observe(1, 2.0)
    assert not gate.observe(1, 2.3)
    assert gate.observe(1, 2.6)


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


def test_registration_config_echoes_capture_generation():
    with TestClient(app) as client, client.websocket_connect(
        "/api/v1/kiosk/stream", headers={"origin": "http://localhost:5173"}
    ) as socket:
        assert socket.receive_json()["event"] == "stream_ready"
        socket.send_json({"event": "CONFIGURE", "payload": {
            "mode": "registration", "session_id": "session-a", "capture_generation": 7,
        }})
        state = socket.receive_json()
        assert state["event"] == "session_state"
        assert state["payload"] == {
            "mode": "registration", "session_id": "session-a", "capture_generation": 7,
        }


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
        self._provider_detections[1] = ProviderFaceDetection((0, 100, 100, 0))
        return None, [{"track_id": 1, "quality_ok": True, "box": [0, 100, 100, 0], "guidance": None}]
    monkeypatch.setattr(VisionEngine, "inspect", inspect)
    result = SimpleNamespace(result="SUCCESS", user_id=uuid4(), confidence_score=.93)
    monkeypatch.setattr(runtime, "load_candidates", lambda: [])
    monkeypatch.setattr(
        RecognitionService,
        "recognize",
        lambda self, image, detections, candidates, quality_accepted: result,
    )
    confirmations = []
    monkeypatch.setattr(runtime, "confirm", lambda session, match: confirmations.append(session) or {"user": {"id": str(match.user_id)}})
    with TestClient(app) as client, client.websocket_connect("/api/v1/kiosk/stream", headers={"origin": "http://localhost:5173"}) as socket:
        assert socket.receive_json()["event"] == "stream_ready"
        socket.send_json({"event": "CONFIGURE", "payload": {"mode": "recognition", "session_id": "test"}})
        read_until(socket, "session_state")
        for index in range(3):
            socket.send_bytes(b"frame")
            events = read_until(socket, "frame_ready")
            assert next(e for e in events if e["event"] == "recognition_finished")["payload"]["session_id"] == "test"
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


def test_production_stream_omits_face_coordinates_and_diagnostics(monkeypatch):
    monkeypatch.setattr(runtime.settings, "face_diagnostics_enabled", False)

    def inspect(self, _data):
        self.tracks[1] = Track(1, (0, 200, 200, 0), 0, 0)
        return np.zeros((200, 200, 3), dtype=np.uint8), [{
            "track_id": 1,
            "quality_ok": False,
            "guidance": "Giữ yên khuôn mặt",
            "box": [0, 200, 200, 0],
            "landmarks": [[50, 50]],
            "quality_metrics": {"brightness": 100},
        }]

    monkeypatch.setattr(VisionEngine, "inspect", inspect)
    with TestClient(app) as client, client.websocket_connect(
        "/api/v1/kiosk/stream", headers={"origin": "http://localhost:5173"}
    ) as socket:
        socket.receive_json()
        socket.send_json({"event": "CONFIGURE", "payload": {"mode": "recognition"}})
        read_until(socket, "session_state")
        socket.send_bytes(b"frame")
        events = read_until(socket, "frame_ready")
        tracking = next(event for event in events if event["event"] == "face_tracking")
        assert tracking["payload"] == {"faces": [{
            "track_id": 1,
            "quality_ok": False,
            "guidance": "Giữ yên khuôn mặt",
        }]}
        quality = next(event for event in events if event["event"] == "face_quality_bad")
        assert "box" not in quality["payload"]
        assert "landmarks" not in quality["payload"]
        assert "quality_metrics" not in quality["payload"]


def test_registration_stream_emits_multiple_face_lock_without_quality_good(monkeypatch):
    def inspect(self, _data):
        for track_id in (1, 2):
            self.tracks.setdefault(track_id, Track(track_id, (0, 100, 100, 0), 0, 0))
        faces = [{"track_id": track_id, "quality_ok": True, "box": [0, 100, 100, 0], "guidance": None}
                 for track_id in (1, 2)]
        return None, faces
    monkeypatch.setattr(VisionEngine, "inspect", inspect)
    with TestClient(app) as client, client.websocket_connect(
        "/api/v1/kiosk/stream", headers={"origin": "http://localhost:5173"}
    ) as socket:
        socket.receive_json()
        socket.send_json({"event": "CONFIGURE", "payload": {"mode": "registration", "session_id": "session-b"}})
        read_until(socket, "session_state")
        socket.send_bytes(b"frame")
        events = read_until(socket, "frame_ready")
        multiple = next(event for event in events if event["event"] == "multiple_faces_detected")
        assert multiple["payload"]["face_count"] == 2
        assert multiple["payload"]["session_id"] == "session-b"
        assert "embedding" not in multiple["payload"]
        assert not any(event["event"] == "face_quality_good" for event in events)


def test_registration_second_face_resets_stability_and_single_face_can_restart(monkeypatch):
    monkeypatch.setattr(runtime.settings, "registration_stable_frames", 2)
    monkeypatch.setattr(runtime.settings, "registration_stable_ms", 0)
    clock = iter(index / 10 for index in range(1000, 2000))
    monkeypatch.setattr(runtime, "monotonic", lambda: next(clock))
    sequence = [(1,), (1, 2), (1,), (1,)]

    def inspect(self, _data):
        track_ids = sequence.pop(0)
        for track_id in track_ids:
            self.tracks.setdefault(track_id, Track(track_id, (0, 200, 200, 0), 0, 0))
        return None, [
            {
                "track_id": track_id,
                "quality_ok": True,
                "box": [0, 200, 200, 0],
                "guidance": None,
            }
            for track_id in track_ids
        ]

    monkeypatch.setattr(VisionEngine, "inspect", inspect)
    with TestClient(app) as client, client.websocket_connect(
        "/api/v1/kiosk/stream", headers={"origin": "http://localhost:5173"}
    ) as socket:
        socket.receive_json()
        socket.send_json({
            "event": "CONFIGURE",
            "payload": {"mode": "registration", "session_id": "session-a"},
        })
        read_until(socket, "session_state")

        frame_events = []
        for _ in range(4):
            socket.send_bytes(b"frame")
            frame_events.append(read_until(socket, "frame_ready"))

        assert not any(event["event"] == "face_quality_good" for event in frame_events[0])
        assert any(event["event"] == "multiple_faces_detected" for event in frame_events[1])
        assert not any(event["event"] == "face_quality_good" for event in frame_events[1])
        assert not any(event["event"] == "face_quality_good" for event in frame_events[2])
        good = next(
            event for event in frame_events[3] if event["event"] == "face_quality_good"
        )
        assert good["payload"]["session_id"] == "session-a"
        assert good["payload"]["stable_frames"] == 2
        assert "embedding" not in good["payload"]
