export const FACE_LATENCY_STAGES = [
  "decode_ms", "detection_ms", "quality_tracking_ms", "embedding_ms",
  "profile_query_ms", "search_ms", "websocket_ui_round_trip_ms", "total_ms",
] as const;

export type FaceLatencyStage = typeof FACE_LATENCY_STAGES[number];
export type FaceLatencySample = Record<FaceLatencyStage, number>;

function percentile(values: number[], fraction: number) {
  if (!values.length) return null;
  const sorted = [...values].sort((left, right) => left - right);
  const position = (sorted.length - 1) * fraction;
  const lower = Math.floor(position); const upper = Math.ceil(position);
  if (lower === upper) return sorted[lower];
  return sorted[lower] + (sorted[upper] - sorted[lower]) * (position - lower);
}

export class FaceLatencyBenchmark {
  private samples: FaceLatencySample[] = [];

  add(sample: FaceLatencySample) {
    if (FACE_LATENCY_STAGES.some(stage => !Number.isFinite(sample[stage]) || sample[stage] < 0)) return false;
    this.samples.push({ ...sample });
    return true;
  }

  summary() {
    return {
      sample_count: this.samples.length,
      stages: Object.fromEntries(FACE_LATENCY_STAGES.map(stage => {
        const values = this.samples.map(sample => sample[stage]);
        return [stage, {
          p50_ms: percentile(values, .5),
          p95_ms: percentile(values, .95),
        }];
      })),
    };
  }
}
