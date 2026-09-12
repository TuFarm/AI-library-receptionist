export type MotionRoi = { x: number; y: number; width: number; height: number };
export type PixelMotionConfig = {
  width: number; height: number; roi: MotionRoi; warmupSamples: number; historySamples: number;
  requiredMotionSamples: number; confirmationMs: number; absenceMs: number; cooldownMs: number;
  pixelDelta: number; enterRatio: number; exitRatio: number; baselineAlpha: number;
};
export type MotionObservation = { warmedUp: boolean; moving: boolean; present: boolean; wake: boolean; lost: boolean; roiMotionRatio: number };
const clamp = (value: number, minimum: number, maximum: number) => Math.max(minimum, Math.min(maximum, value));

/** Local-only detector. Frame data is never logged, retained outside this object, or transmitted. */
export class PixelMotionDetector {
  private baseline: Float32Array | null = null;
  private warmupCount = 0;
  private history: boolean[] = [];
  private firstEvidenceAt: number | null = null;
  private lastActivityAt: number | null = null;
  private moving = false;
  private present = false;
  private cooldownUntil = 0;
  constructor(private readonly config: PixelMotionConfig) {}
  reset() { this.baseline = null; this.warmupCount = 0; this.history = []; this.firstEvidenceAt = null; this.lastActivityAt = null; this.moving = false; this.present = false; this.cooldownUntil = 0; }

  observe(frame: Uint8ClampedArray, now: number, auxiliaryFace = false): MotionObservation {
    const { width, height } = this.config;
    if (frame.length !== width * height) throw new Error("Kích thước motion frame không hợp lệ.");
    if (!this.baseline) this.baseline = Float32Array.from(frame);
    if (this.warmupCount < this.config.warmupSamples) {
      this.warmupCount += 1;
      const alpha = 1 / this.warmupCount;
      for (let index = 0; index < frame.length; index += 1) this.baseline[index] += (frame[index] - this.baseline[index]) * alpha;
      return this.result(false, false, false, 0);
    }

    let globalShift = 0;
    for (let index = 0; index < frame.length; index += 1) globalShift += frame[index] - this.baseline[index];
    globalShift /= frame.length;
    const roi = this.config.roi;
    const left = clamp(Math.floor(roi.x * width), 0, width - 1);
    const top = clamp(Math.floor(roi.y * height), 0, height - 1);
    const right = clamp(Math.ceil((roi.x + roi.width) * width), left + 1, width);
    const bottom = clamp(Math.ceil((roi.y + roi.height) * height), top + 1, height);
    let changed = 0; let samples = 0;
    for (let y = top; y < bottom; y += 1) for (let x = left; x < right; x += 1) {
      const index = y * width + x;
      if (Math.abs(frame[index] - this.baseline[index] - globalShift) >= this.config.pixelDelta) changed += 1;
      samples += 1;
    }
    const ratio = samples ? changed / samples : 0;
    this.moving = ratio >= (this.moving ? this.config.exitRatio : this.config.enterRatio);
    this.history.push(this.moving);
    if (this.history.length > this.config.historySamples) this.history.shift();
    if (this.moving) { this.firstEvidenceAt ??= now; this.lastActivityAt = now; }
    else if (this.present && auxiliaryFace) this.lastActivityAt = now;
    else if (!this.history.some(Boolean)) this.firstEvidenceAt = null;

    const enoughSamples = this.history.filter(Boolean).length >= this.config.requiredMotionSamples;
    const sustained = this.firstEvidenceAt !== null && now - this.firstEvidenceAt >= this.config.confirmationMs;
    let wake = false;
    if (!this.present && enoughSamples && sustained) {
      this.present = true; wake = now >= this.cooldownUntil;
      if (wake) this.cooldownUntil = now + this.config.cooldownMs;
    }
    let lost = false;
    if (this.present && this.lastActivityAt !== null && now - this.lastActivityAt >= this.config.absenceMs) {
      this.present = false; this.history = []; this.firstEvidenceAt = null; lost = true;
    }
    if (!this.moving) for (let index = 0; index < frame.length; index += 1) this.baseline[index] += (frame[index] - this.baseline[index]) * this.config.baselineAlpha;
    return this.result(wake, lost, this.moving, ratio);
  }
  private result(wake: boolean, lost: boolean, moving: boolean, roiMotionRatio: number): MotionObservation {
    return { warmedUp: this.warmupCount >= this.config.warmupSamples, moving, present: this.present, wake, lost, roiMotionRatio };
  }
}
