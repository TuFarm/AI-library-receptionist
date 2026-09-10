export const ENROLLMENT_EVIDENCE_TTL_MS = 1500;

export type EnrollmentEvidence = {
  blob: Blob; sessionId: string; trackId: number; issuedAt: number; generation: number;
  stableFrames: number; stableMs: number;
};

export type EnrollmentObservation = {
  sessionId: string; trackId: number; now: number; generation: number; faceCount: number;
  multipleFacesDetected: boolean; qualityReady: boolean; stableFrames: number; stableMs: number;
  requiredStableFrames: number; requiredStableMs: number;
};

export class EnrollmentEvidenceGuard {
  private generation = 0;
  private activeSessionId: string | null = null;
  private captureStartedAt: number | null = null;
  private acknowledgedGeneration: number | null = null;
  private evidence: EnrollmentEvidence | null = null;

  beginCapture(sessionId: string | undefined, now: number) {
    this.generation += 1;
    this.activeSessionId = sessionId ?? null;
    this.captureStartedAt = sessionId ? now : null;
    this.acknowledgedGeneration = null;
    this.evidence = null;
    return this.generation;
  }

  acknowledge(generation: number, sessionId: string | undefined) {
    if (generation !== this.generation || !sessionId || sessionId !== this.activeSessionId) return false;
    this.acknowledgedGeneration = generation;
    return true;
  }

  accept(blob: Blob, observation: EnrollmentObservation) {
    if (!this.isCurrentObservation(observation) || observation.faceCount !== 1 || observation.multipleFacesDetected ||
        !observation.qualityReady || observation.stableFrames < observation.requiredStableFrames ||
        observation.stableMs < observation.requiredStableMs) {
      this.evidence = null;
      return false;
    }
    this.evidence = { blob, sessionId: observation.sessionId, trackId: observation.trackId,
      issuedAt: observation.now, generation: observation.generation,
      stableFrames: observation.stableFrames, stableMs: observation.stableMs };
    return true;
  }

  invalidateEvidence() { this.evidence = null; }

  endCapture() {
    this.generation += 1;
    this.activeSessionId = null;
    this.captureStartedAt = null;
    this.acknowledgedGeneration = null;
    this.evidence = null;
  }

  capture(sessionId: string | undefined, generation: number, preparationMs: number, faceCount: number,
      trackId: number | null, multipleFacesDetected: boolean, now: number) {
    const evidence = this.evidence;
    if (!sessionId || generation !== this.generation || this.acknowledgedGeneration !== generation ||
        this.activeSessionId !== sessionId || this.captureStartedAt === null || now - this.captureStartedAt < preparationMs ||
        faceCount !== 1 || multipleFacesDetected || !evidence || evidence.sessionId !== sessionId ||
        evidence.trackId !== trackId || evidence.generation !== generation || now - evidence.issuedAt > ENROLLMENT_EVIDENCE_TTL_MS) {
      this.evidence = null;
      throw new Error("Vui lòng để đúng một người trong khung hình và giữ yên.");
    }
    this.evidence = null;
    return evidence.blob;
  }

  currentGeneration() { return this.generation; }

  private isCurrentObservation(observation: EnrollmentObservation) {
    return observation.generation === this.generation && this.acknowledgedGeneration === this.generation &&
      observation.sessionId === this.activeSessionId && this.captureStartedAt !== null && observation.now >= this.captureStartedAt;
  }
}
