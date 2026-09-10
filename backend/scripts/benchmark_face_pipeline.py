"""Privacy-safe Face ID latency benchmark; never prints frames or templates."""

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path
from time import perf_counter
from uuid import uuid4

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.vision.benchmark import FACE_BENCHMARK_STAGES, summarize_face_benchmark


def elapsed_ms(started: float) -> float:
    return (perf_counter() - started) * 1000


def mock_sample() -> dict[str, float]:
    """Measures harness overhead only; this is not a biometric performance result."""
    total_started = perf_counter()
    started = perf_counter(); frame = bytes(64 * 1024); decode_ms = elapsed_ms(started)
    started = perf_counter(); faces = [(0, 200, 200, 0)]; detection_ms = elapsed_ms(started)
    started = perf_counter(); accepted = len(faces) == 1; quality_ms = elapsed_ms(started)
    started = perf_counter(); template = hashlib.sha256(frame).digest(); embedding_ms = elapsed_ms(started)
    started = perf_counter(); gallery = [template] * 100; query_ms = elapsed_ms(started)
    started = perf_counter(); _matched = accepted and template in gallery; search_ms = elapsed_ms(started)
    started = perf_counter(); json.loads(json.dumps({"result": "SUCCESS"})); client_ms = elapsed_ms(started)
    return {
        "decode_ms": decode_ms,
        "detection_ms": detection_ms,
        "quality_tracking_ms": quality_ms,
        "embedding_ms": embedding_ms,
        "profile_query_ms": query_ms,
        "search_ms": search_ms,
        "websocket_ui_round_trip_ms": client_ms,
        "total_ms": elapsed_ms(total_started),
    }


async def receive_event(socket, wanted: set[str], timeout_seconds: float):
    while True:
        raw = await asyncio.wait_for(socket.recv(), timeout_seconds)
        if not isinstance(raw, str):
            continue
        message = json.loads(raw)
        event = message.get("event")
        if event == "stream_error":
            raise RuntimeError("Realtime Face ID reported a safe processing error")
        if event in wanted:
            return message


async def websocket_sample(args, image_bytes: bytes) -> dict[str, float]:
    try:
        import websockets
    except ImportError:
        raise RuntimeError("Install the existing backend requirements with uvicorn[standard]") from None

    async with websockets.connect(
        args.ws_url,
        origin=args.origin,
        max_size=3_000_000,
        open_timeout=args.timeout_seconds,
    ) as socket:
        await receive_event(socket, {"stream_ready"}, args.timeout_seconds)
        await socket.send(json.dumps({
            "event": "CONFIGURE",
            "payload": {"mode": "recognition", "session_id": str(uuid4())},
        }))
        await receive_event(socket, {"session_state"}, args.timeout_seconds)
        stable_at = None
        latest_vision = None
        latest_recognition = None
        confirmed_at = None
        for _frame_index in range(args.max_frames):
            sent_at = perf_counter()
            await socket.send(image_bytes)
            frame_ready = False
            while not frame_ready:
                raw = await asyncio.wait_for(socket.recv(), args.timeout_seconds)
                if not isinstance(raw, str):
                    continue
                message = json.loads(raw)
                event, payload = message.get("event"), message.get("payload", {})
                if event == "stream_error":
                    raise RuntimeError("Realtime Face ID reported a safe processing error")
                if event == "face_tracking":
                    latest_vision = payload.get("metrics")
                elif event == "face_quality_good" and stable_at is None:
                    stable_at = perf_counter()
                elif event == "recognition_finished" and payload.get("result") != "ERROR":
                    latest_recognition = payload
                elif event == "identity_candidate" and payload.get("confirmed") is True:
                    confirmed_at = perf_counter()
                elif event == "frame_ready":
                    frame_ready = True
            if confirmed_at is not None and latest_recognition is not None and stable_at is not None and latest_vision is not None:
                if latest_recognition.get("face_provider") != "opencv-sface-128d":
                    raise RuntimeError("Backend did not report the requested OpenCV provider")
                sample = {
                    "decode_ms": latest_vision["decode_ms"],
                    "detection_ms": latest_vision["detection_ms"],
                    "quality_tracking_ms": latest_vision["quality_tracking_ms"],
                    "embedding_ms": latest_recognition["embedding_ms"],
                    "profile_query_ms": latest_recognition["profile_query_ms"],
                    "search_ms": latest_recognition["search_ms"],
                    "websocket_ui_round_trip_ms": (confirmed_at - sent_at) * 1000,
                    "total_ms": (confirmed_at - stable_at) * 1000,
                }
                return {stage: float(sample[stage]) for stage in FACE_BENCHMARK_STAGES}
            await asyncio.sleep(args.frame_interval_ms / 1000)
    raise RuntimeError("No three-vote identity confirmation arrived within the configured frame limit")


async def run(args):
    if args.provider == "mock":
        samples = [mock_sample() for _ in range(args.warmup + args.iterations)]
        scope = "non_biometric_harness_only"
    else:
        if args.image is None or not args.image.is_file():
            raise RuntimeError("local_opencv requires a readable, consented --image fixture")
        image_bytes = args.image.read_bytes()
        if len(image_bytes) > 2_500_000:
            raise RuntimeError("Benchmark frame exceeds the kiosk WebSocket size limit")
        samples = []
        for _index in range(args.warmup + args.iterations):
            samples.append(await websocket_sample(args, image_bytes))
        scope = "real_opencv_models_over_websocket"
    measured = samples[args.warmup:]
    report = summarize_face_benchmark(
        measured, target_total_p95_ms=args.target_total_p95_ms
    )
    if args.provider == "mock":
        report["target_met"] = None
    report.update({
        "provider": args.provider,
        "scope": scope,
        "warmup_count": args.warmup,
        "target_evaluated": args.provider == "local_opencv",
        "cpu_baseline": args.provider == "local_opencv",
        "contains_biometric_payload": False,
        "ui_metric_note": (
            "Mock timings validate benchmark plumbing only; they do not measure vote confirmation."
            if args.provider == "mock" else
            "Measures through the server's three-vote candidate confirmation; use kiosk "
            "diagnostics faceLatencyBenchmark for Chromium next-paint timing."
        ),
    })
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["target_met"] or args.provider == "mock" else 2


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("mock", "local_opencv"), required=True)
    parser.add_argument("--image", type=Path)
    parser.add_argument("--ws-url", default="ws://127.0.0.1:8000/api/v1/kiosk/stream")
    parser.add_argument("--origin", default="http://127.0.0.1:5173")
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--frame-interval-ms", type=float, default=100.0)
    parser.add_argument("--max-frames", type=int, default=30)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--target-total-p95-ms", type=float, default=3000.0)
    args = parser.parse_args()
    if args.iterations < 1 or args.warmup < 0 or args.max_frames < 1:
        parser.error("iterations/max-frames must be positive and warmup cannot be negative")
    return args


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(run(parse_args())))
    except RuntimeError as exc:
        print(f"Benchmark failed safely: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    except (OSError, ValueError, KeyError):
        print("Benchmark failed safely because an input or runtime dependency is unavailable.", file=sys.stderr)
        raise SystemExit(1) from None
