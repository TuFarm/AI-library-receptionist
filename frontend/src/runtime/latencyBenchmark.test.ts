import { describe, expect, it } from "vitest";
import { FaceLatencyBenchmark } from "./latencyBenchmark";

describe("Face ID latency benchmark", () => {
  it("reports P50/P95 without retaining biometric payloads", () => {
    const benchmark = new FaceLatencyBenchmark();
    for (const multiplier of [1, 2, 3, 4, 5]) {
      expect(benchmark.add({
        decode_ms: multiplier, detection_ms: multiplier * 2,
        quality_tracking_ms: multiplier * 3, embedding_ms: multiplier * 4,
        profile_query_ms: multiplier * 5, search_ms: multiplier * 6,
        websocket_ui_round_trip_ms: multiplier * 7, total_ms: multiplier * 8,
      })).toBe(true);
    }
    const summary = benchmark.summary();
    expect(summary.sample_count).toBe(5);
    expect(summary.stages.total_ms).toEqual({ p50_ms: 24, p95_ms: 38.4 });
    expect(JSON.stringify(summary)).not.toContain("embedding_values");
    expect(JSON.stringify(summary)).not.toContain("image");
  });

  it("drops invalid timing samples", () => {
    const benchmark = new FaceLatencyBenchmark();
    expect(benchmark.add({
      decode_ms: -1, detection_ms: 1, quality_tracking_ms: 1, embedding_ms: 1,
      profile_query_ms: 1, search_ms: 1, websocket_ui_round_trip_ms: 1, total_ms: 1,
    })).toBe(false);
    expect(benchmark.summary().sample_count).toBe(0);
  });
});
