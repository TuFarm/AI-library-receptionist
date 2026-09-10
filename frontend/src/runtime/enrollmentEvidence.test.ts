import { describe, expect, it } from "vitest";
import { ENROLLMENT_EVIDENCE_TTL_MS, EnrollmentEvidenceGuard } from "./enrollmentEvidence";

describe("enrollment evidence", () => {
  const frameA = new Blob(["person-a"]);

  it("is bound to registration session, single face, track and expiry", () => {
    const invalidCaptures: Array<[string | undefined, boolean, number, number | null, number]> = [
      ["session-b", true, 1, 7, 101],
      ["session-a", true, 2, 7, 101],
      ["session-a", true, 1, 8, 101],
      ["session-a", true, 1, 7, 100 + ENROLLMENT_EVIDENCE_TTL_MS + 1],
    ];
    for (const args of invalidCaptures) {
      const guard = new EnrollmentEvidenceGuard();
      guard.accept(frameA, "session-a", 7, 100);
      expect(() => guard.capture(...args)).toThrow();
      expect(() => guard.capture("session-a", true, 1, 7, 101)).toThrow();
    }
  });

  it("cannot reuse an old frame after a second face resets evidence", () => {
    const guard = new EnrollmentEvidenceGuard();
    guard.accept(frameA, "session-a", 7, 100);
    guard.invalidate();
    expect(() => guard.capture("session-a", true, 1, 7, 101)).toThrow();
    const newFrameA = new Blob(["person-a-new-stability-window"]);
    guard.accept(newFrameA, "session-a", 7, 200);
    expect(guard.capture("session-a", true, 1, 7, 201)).toBe(newFrameA);
    expect(() => guard.capture("session-a", true, 1, 7, 202)).toThrow();
  });
});
