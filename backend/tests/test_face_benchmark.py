import asyncio
import json
import sys
from types import SimpleNamespace

import pytest

from app.vision.benchmark import FACE_BENCHMARK_STAGES, percentile, summarize_face_benchmark
from scripts.benchmark_face_pipeline import websocket_sample


def sample(multiplier: float):
    return {stage: multiplier * (index + 1) for index, stage in enumerate(FACE_BENCHMARK_STAGES)}


def test_benchmark_reports_p50_p95_and_target_without_sensitive_values():
    report = summarize_face_benchmark([sample(value) for value in (1, 2, 3, 4, 5)])
    assert report["sample_count"] == 5
    assert report["stages"]["decode_ms"] == {"p50_ms": 3.0, "p95_ms": 4.8}
    assert report["stages"]["total_ms"] == {"p50_ms": 24.0, "p95_ms": 38.4}
    assert report["target_met"] is True
    assert "image" not in str(report)
    assert "embedding_values" not in str(report)


def test_benchmark_target_fails_when_total_p95_exceeds_three_seconds():
    report = summarize_face_benchmark([sample(500)])
    assert report["stages"]["total_ms"]["p95_ms"] == 4000.0
    assert report["target_met"] is False


def test_benchmark_rejects_invalid_samples_and_percentile_handles_empty_input():
    invalid = sample(1)
    invalid["search_ms"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        summarize_face_benchmark([invalid])
    assert percentile([], 0.95) is None


def test_real_harness_waits_for_three_vote_confirmation(monkeypatch):
    metrics = {"decode_ms": 1, "detection_ms": 2, "quality_tracking_ms": 3}
    recognition = {
        "result": "SUCCESS", "face_provider": "opencv-sface-128d",
        "embedding_ms": 4, "profile_query_ms": 5, "search_ms": 6,
    }

    class Socket:
        def __init__(self):
            self.messages = [json.dumps({"event": "stream_ready", "payload": {}})]
            self.frames = 0

        async def send(self, value):
            if isinstance(value, str):
                self.messages.append(json.dumps({"event": "session_state", "payload": {}}))
                return
            self.frames += 1
            confirmed = self.frames == 3
            self.messages.extend(json.dumps(message) for message in (
                {"event": "face_tracking", "payload": {"metrics": metrics}},
                {"event": "face_quality_good", "payload": {}},
                {"event": "recognition_finished", "payload": recognition},
                {"event": "identity_candidate", "payload": {"confirmed": confirmed}},
                {"event": "frame_ready", "payload": {}},
            ))

        async def recv(self):
            return self.messages.pop(0)

    socket = Socket()

    class Connection:
        async def __aenter__(self): return socket
        async def __aexit__(self, *_args): return None

    monkeypatch.setitem(
        sys.modules, "websockets", SimpleNamespace(connect=lambda *_args, **_kwargs: Connection())
    )
    args = SimpleNamespace(
        ws_url="ws://test", origin="http://test", timeout_seconds=1,
        max_frames=3, frame_interval_ms=0,
    )
    result = asyncio.run(websocket_sample(args, b"frame"))
    assert socket.frames == 3
    assert result["embedding_ms"] == 4
    assert result["total_ms"] >= 0
