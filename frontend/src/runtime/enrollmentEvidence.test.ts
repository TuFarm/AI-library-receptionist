import { describe, expect, it } from "vitest";
import { ENROLLMENT_EVIDENCE_TTL_MS, EnrollmentEvidenceGuard, type EnrollmentObservation } from "./enrollmentEvidence";

const frame = (name: string) => new Blob([name]);
const observation = (generation: number, overrides: Partial<EnrollmentObservation> = {}): EnrollmentObservation => ({
  sessionId: "session-a", trackId: 7, now: 1000, generation, faceCount: 1,
  multipleFacesDetected: false, qualityReady: true, stableFrames: 5, stableMs: 700,
  requiredStableFrames: 5, requiredStableMs: 700, ...overrides,
});
describe("capture-scoped enrollment evidence", () => {
  it("rejects evidence collected while the information form is open", () => {
    const guard = new EnrollmentEvidenceGuard();
    expect(guard.accept(frame("form"), observation(0))).toBe(false);
  });

  it("opening capture invalidates old evidence and waits for the new registration acknowledgement", () => {
    const guard = new EnrollmentEvidenceGuard();
    const first = guard.beginCapture("session-a", 0);
    expect(guard.accept(frame("before-ack"), observation(first))).toBe(false);
    expect(guard.acknowledge(first, "session-a")).toBe(true);
    expect(guard.accept(frame("fresh"), observation(first))).toBe(true);
  });

  it("cannot capture before the minimum preparation time", () => {
    const guard = new EnrollmentEvidenceGuard();
    const generation = guard.beginCapture("session-a", 0);
    guard.acknowledge(generation, "session-a");
    guard.accept(frame("stable"), observation(generation, { now: 1000 }));
    expect(() => guard.capture("session-a", generation, 1800, 1, 7, false, 1799)).toThrow();
  });

  it("captures once only after a fresh, stable, exact-one-face observation", () => {
    const guard = new EnrollmentEvidenceGuard();
    const generation = guard.beginCapture("session-a", 0);
    guard.acknowledge(generation, "session-a");
    expect(guard.accept(frame("too-few"), observation(generation, { stableFrames: 4 }))).toBe(false);
    const stable = frame("stable");
    expect(guard.accept(stable, observation(generation, { now: 1800 }))).toBe(true);
    expect(guard.capture("session-a", generation, 1800, 1, 7, false, 1801)).toBe(stable);
    expect(() => guard.capture("session-a", generation, 1800, 1, 7, false, 1802)).toThrow();
  });

  it("multiple faces reset evidence and require a new generation", () => {
    const guard = new EnrollmentEvidenceGuard();
    const oldGeneration = guard.beginCapture("session-a", 0);
    guard.acknowledge(oldGeneration, "session-a");
    guard.accept(frame("old"), observation(oldGeneration, { now: 1800 }));
    const newGeneration = guard.beginCapture("session-a", 1800);
    expect(newGeneration).not.toBe(oldGeneration);
    expect(() => guard.capture("session-a", oldGeneration, 1800, 1, 7, false, 1801)).toThrow();
    guard.acknowledge(newGeneration, "session-a");
    expect(guard.accept(frame("multiple"), observation(newGeneration, { now: 2000, faceCount: 2, multipleFacesDetected: true }))).toBe(false);
  });

  it("returning to the form rejects the prior capture generation and expired evidence", () => {
    const guard = new EnrollmentEvidenceGuard();
    const first = guard.beginCapture("session-a", 0);
    guard.acknowledge(first, "session-a");
    guard.accept(frame("first"), observation(first, { now: 1800 }));
    guard.endCapture();
    const second = guard.beginCapture("session-a", 2000);
    guard.acknowledge(second, "session-a");
    expect(() => guard.capture("session-a", first, 1800, 1, 7, false, 2001)).toThrow();
    guard.accept(frame("expired"), observation(second, { now: 2000 }));
    expect(() => guard.capture("session-a", second, 1800, 1, 7, false, 2000 + ENROLLMENT_EVIDENCE_TTL_MS + 1)).toThrow();
  });
});
