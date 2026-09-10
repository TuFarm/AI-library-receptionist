import { describe, expect, it } from "vitest";
import { UnknownRecognitionGuard, type UnknownRecognitionContext } from "./recognitionUnknown";

const valid = (overrides: Partial<UnknownRecognitionContext> = {}): UnknownRecognitionContext => ({
  sessionId: "session-a", trackId: 4, faceCount: 1, qualityReady: true,
  recognitionActive: true, identityPending: false, ...overrides,
});

describe("safe unknown-face decision", () => {
  it("requires three safe results and the minimum recognition time", () => {
    const guard = new UnknownRecognitionGuard(4000, 3);
    expect(guard.observe("UNKNOWN_FACE", valid(), 100)).toBe(false);
    expect(guard.observe("LOW_CONFIDENCE", valid(), 600)).toBe(false);
    expect(guard.observe("UNKNOWN_FACE", valid(), 1100)).toBe(false);
    expect(guard.isReady(valid(), 4099)).toBe(false);
    expect(guard.isReady(valid(), 4100)).toBe(true);
  });

  it("does not decide with too few attempts, too little time, no face or poor quality", () => {
    const guard = new UnknownRecognitionGuard(4000, 3);
    guard.observe("UNKNOWN_FACE", valid(), 0);
    guard.observe("UNKNOWN_FACE", valid(), 500);
    expect(guard.isReady(valid(), 5000)).toBe(false);
    expect(guard.observe("UNKNOWN_FACE", valid({ faceCount: 0 }), 5100)).toBe(false);
    expect(guard.snapshot().attempts).toBe(0);
    expect(guard.observe("UNKNOWN_FACE", valid({ qualityReady: false }), 5200)).toBe(false);
  });

  it.each([
    ["multiple face", valid({ faceCount: 2 })],
    ["track change", valid({ trackId: 9 })],
    ["session change", valid({ sessionId: "session-b" })],
    ["reconnect/provider reset", null],
  ])("resets on %s", (_name, changed) => {
    const guard = new UnknownRecognitionGuard(4000, 3);
    guard.observe("UNKNOWN_FACE", valid(), 0);
    guard.observe("UNKNOWN_FACE", valid(), 500);
    if (changed) guard.observe("UNKNOWN_FACE", changed, 1000);
    else guard.reset();
    expect(guard.snapshot().attempts).toBe(changed && changed.faceCount === 1 && changed.qualityReady ? 1 : 0);
    expect(guard.isReady(changed ?? valid(), 5000)).toBe(false);
  });

  it("blocks unknown when an identity candidate or confirmation is pending", () => {
    const guard = new UnknownRecognitionGuard(4000, 3);
    guard.observe("UNKNOWN_FACE", valid(), 0);
    guard.observe("LOW_CONFIDENCE", valid(), 500);
    guard.observe("UNKNOWN_FACE", valid(), 1000);
    guard.markCandidate("session-a", 4);
    expect(guard.isReady(valid(), 5000)).toBe(false);
    expect(guard.isReady(valid({ identityPending: true }), 5000)).toBe(false);
    guard.reset();
    expect(guard.isReady(valid(), 5000)).toBe(false);
  });

  it("resets immediately when a known identity result arrives", () => {
    const guard = new UnknownRecognitionGuard(4000, 3);
    guard.observe("UNKNOWN_FACE", valid(), 0);
    guard.observe("SUCCESS", valid(), 500);
    expect(guard.snapshot().attempts).toBe(0);
  });
});
