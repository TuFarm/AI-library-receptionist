import { describe, expect, it } from "vitest";
import { PixelMotionDetector, type PixelMotionConfig } from "./pixelMotionDetector";

const config: PixelMotionConfig = {
  width: 10, height: 10, roi: { x: .2, y: .2, width: .6, height: .6 }, warmupSamples: 2,
  historySamples: 8, requiredMotionSamples: 6, confirmationMs: 1200, absenceMs: 9000,
  cooldownMs: 1000, pixelDelta: 15, enterRatio: .08, exitRatio: .04, baselineAlpha: .025,
};
const frame = (value = 0) => new Uint8ClampedArray(100).fill(value);
const withRect = (left: number, top: number, width: number, height: number, value = 60) => {
  const pixels = frame();
  for (let y = top; y < top + height; y += 1) for (let x = left; x < left + width; x += 1) pixels[y * 10 + x] = value;
  return pixels;
};
const warmed = () => { const detector = new PixelMotionDetector(config); detector.observe(frame(), 0); detector.observe(frame(), 200); return detector; };

describe("pixel motion presence detector", () => {
  it("warms the adaptive baseline before accepting motion", () => {
    const detector = new PixelMotionDetector(config);
    expect(detector.observe(withRect(2, 2, 6, 6), 0).warmedUp).toBe(false);
    expect(detector.observe(withRect(2, 2, 6, 6), 200).wake).toBe(false);
  });
  it("accepts sustained ROI motion only after the 6/8 and time gates", () => {
    const detector = warmed(); const subject = withRect(2, 2, 6, 6);
    for (let index = 0; index < 6; index += 1) expect(detector.observe(subject, 400 + index * 200).wake).toBe(false);
    const accepted = detector.observe(subject, 1600);
    expect(accepted.wake).toBe(true); expect(accepted.present).toBe(true);
    expect(detector.observe(subject, 1800).wake).toBe(false);
  });
  it("ignores motion outside the configured ROI and whole-frame flicker", () => {
    const outside = warmed();
    for (let time = 400; time <= 1800; time += 200) expect(outside.observe(withRect(0, 0, 1, 10), time).wake).toBe(false);
    const flicker = warmed();
    for (let time = 400; time <= 1800; time += 200) {
      const observation = flicker.observe(frame(45), time);
      expect(observation.moving).toBe(false); expect(observation.wake).toBe(false);
    }
  });
  it("uses a lower exit threshold to avoid presence chatter", () => {
    const detector = new PixelMotionDetector({ ...config, roi: { x: 0, y: 0, width: 1, height: 1 }, warmupSamples: 1 });
    detector.observe(frame(), 0);
    expect(detector.observe(withRect(0, 0, 1, 10), 200).moving).toBe(true);
    expect(detector.observe(withRect(0, 0, 1, 5), 400).moving).toBe(true);
    expect(detector.observe(withRect(0, 0, 1, 3), 600).moving).toBe(false);
  });
  it("holds presence through brief gaps and emits loss at nine seconds", () => {
    const detector = warmed(); const subject = withRect(2, 2, 6, 6);
    for (let time = 400; time <= 1600; time += 200) detector.observe(subject, time);
    expect(detector.observe(frame(), 3000).lost).toBe(false);
    const lost = detector.observe(frame(), 10_601);
    expect(lost.lost).toBe(true); expect(lost.present).toBe(false);
  });
  it("never lets optional native face detection replace mandatory pixel motion", () => {
    const detector = warmed();
    for (let index = 0; index < 6; index += 1) expect(detector.observe(frame(), 400 + index * 200, true).wake).toBe(false);
    expect(detector.observe(frame(), 1600, true).wake).toBe(false);
  });
});
