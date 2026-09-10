import math
from collections.abc import Iterable, Mapping


FACE_BENCHMARK_STAGES = (
    "decode_ms",
    "detection_ms",
    "quality_tracking_ms",
    "embedding_ms",
    "profile_query_ms",
    "search_ms",
    "websocket_ui_round_trip_ms",
    "total_ms",
)


def percentile(values: Iterable[float], fraction: float) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * fraction
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summarize_face_benchmark(
    samples: Iterable[Mapping[str, float]], *, target_total_p95_ms: float = 3000.0
) -> dict:
    safe_samples = []
    for sample in samples:
        values = {stage: float(sample[stage]) for stage in FACE_BENCHMARK_STAGES}
        if not all(math.isfinite(value) and value >= 0 for value in values.values()):
            raise ValueError("Benchmark timing samples must be finite and non-negative")
        safe_samples.append(values)
    stages = {
        stage: {
            "p50_ms": round(percentile((sample[stage] for sample in safe_samples), 0.5) or 0.0, 3),
            "p95_ms": round(percentile((sample[stage] for sample in safe_samples), 0.95) or 0.0, 3),
        }
        for stage in FACE_BENCHMARK_STAGES
    }
    total_p95 = stages["total_ms"]["p95_ms"] if safe_samples else None
    return {
        "sample_count": len(safe_samples),
        "target_total_p95_ms": target_total_p95_ms,
        "target_met": total_p95 is not None and total_p95 <= target_total_p95_ms,
        "stages": stages,
    }
