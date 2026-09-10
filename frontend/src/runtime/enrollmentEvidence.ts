export const ENROLLMENT_EVIDENCE_TTL_MS = 1500;

export type EnrollmentEvidence = {
  blob: Blob;
  sessionId: string;
  trackId: number;
  issuedAt: number;
  generation: number;
};

export class EnrollmentEvidenceGuard {
  private generation = 0;
  private evidence: EnrollmentEvidence | null = null;

  accept(blob: Blob, sessionId: string, trackId: number, now: number) {
    this.evidence = { blob, sessionId, trackId, issuedAt: now, generation: this.generation };
  }

  invalidate() {
    this.generation += 1;
    this.evidence = null;
  }

  capture(sessionId: string | undefined, registration: boolean, faceCount: number, trackId: number | null, now: number) {
    const evidence = this.evidence;
    if (!registration || !sessionId || faceCount !== 1 || !evidence ||
        evidence.sessionId !== sessionId || evidence.trackId !== trackId || evidence.generation !== this.generation ||
        now - evidence.issuedAt > ENROLLMENT_EVIDENCE_TTL_MS) {
      this.invalidate();
      throw new Error("Vui lòng để đúng một người trong khung hình và giữ yên.");
    }
    this.invalidate(); // A successful capture is single-use.
    return evidence.blob;
  }
}
