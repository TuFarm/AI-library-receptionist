export type UnknownRecognitionContext = {
  sessionId?: string;
  trackId: number | null;
  faceCount: number;
  qualityReady: boolean;
  recognitionActive: boolean;
  identityPending: boolean;
};

export class UnknownRecognitionGuard {
  private sessionId: string | null = null;
  private trackId: number | null = null;
  private attempts = 0;
  private firstResultAt: number | null = null;
  private candidatePending = false;

  constructor(private readonly minimumMs: number, private readonly requiredAttempts: number) {}

  reset() {
    this.sessionId = null;
    this.trackId = null;
    this.attempts = 0;
    this.firstResultAt = null;
    this.candidatePending = false;
  }

  markCandidate(sessionId: string | undefined, trackId: number | null) {
    if (sessionId && sessionId === this.sessionId && trackId === this.trackId) this.candidatePending = true;
  }

  observe(result: unknown, context: UnknownRecognitionContext, now: number) {
    if (!this.validContext(context)) {
      this.reset();
      return false;
    }
    if (this.sessionId !== context.sessionId || this.trackId !== context.trackId) {
      this.reset();
      this.sessionId = context.sessionId!;
      this.trackId = context.trackId;
    }
    if (result !== "UNKNOWN_FACE" && result !== "LOW_CONFIDENCE") {
      this.reset();
      return false;
    }
    this.candidatePending = false;
    this.firstResultAt ??= now;
    this.attempts += 1;
    return this.isReady(context, now);
  }

  isReady(context: UnknownRecognitionContext, now: number) {
    return this.validContext(context) && context.sessionId === this.sessionId && context.trackId === this.trackId &&
      !this.candidatePending && !context.identityPending && this.firstResultAt !== null &&
      this.attempts >= this.requiredAttempts && now - this.firstResultAt >= this.minimumMs;
  }

  delayUntilEligible(now: number) {
    if (this.firstResultAt === null || this.attempts < this.requiredAttempts || this.candidatePending) return null;
    return Math.max(0, this.minimumMs - (now - this.firstResultAt));
  }

  snapshot() {
    return { attempts: this.attempts, firstResultAt: this.firstResultAt, sessionId: this.sessionId, trackId: this.trackId };
  }

  private validContext(context: UnknownRecognitionContext) {
    return Boolean(context.sessionId) && context.trackId !== null && context.faceCount === 1 &&
      context.qualityReady && context.recognitionActive;
  }
}
