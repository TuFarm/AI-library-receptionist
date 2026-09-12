function positiveEnvNumber(value: unknown, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export const KIOSK_RECOGNITION = {
  unknownMinMs: positiveEnvNumber(import.meta.env.VITE_KIOSK_UNKNOWN_MIN_MS, 4000),
  unknownAttempts: Math.ceil(positiveEnvNumber(import.meta.env.VITE_KIOSK_UNKNOWN_ATTEMPTS, 3)),
} as const;

export const KIOSK_ENROLLMENT = {
  capturePreparationMs: positiveEnvNumber(import.meta.env.VITE_KIOSK_CAPTURE_PREPARATION_MS, 1800),
  stableFrames: Math.ceil(positiveEnvNumber(import.meta.env.VITE_KIOSK_REGISTRATION_STABLE_FRAMES, 5)),
  stableMs: positiveEnvNumber(import.meta.env.VITE_KIOSK_REGISTRATION_STABLE_MS, 700),
} as const;

export const KIOSK_TIMING = {
  presenceConfirmationMs: 1200,
  presenceSampleMs: 200,
  presenceAbsenceMs: 9000,
  presenceWakeCooldownMs: 1000,
  cameraPreparationMs: 1000,
  faceStableMs: 1200,
  faceSampleMs: 160,
  countdownStepMs: 500,
  minimumVerificationMs: 1000,
  recognitionCooldownMs: 2000,
  welcomeDisplayMs: 2500,
  postSpeechSilenceMs: 500,
  registrationSuccessMs: 2200,
  registrationSpeechMaxMs: 8000,
  thankYouMs: 3000,
  returnIdleMs: 500,
  transitionMs: 420,
} as const;

export const KIOSK_MOTION = {
  canvasWidth: 96,
  canvasHeight: 54,
  warmupSamples: 8,
  historySamples: 8,
  requiredMotionSamples: 6,
  pixelDelta: 14,
  enterRatio: 0.08,
  exitRatio: 0.04,
  baselineAlpha: 0.025,
  nativeFaceSampleMs: 1000,
  roi: { x: 0.2, y: 0.08, width: 0.6, height: 0.84 },
  stableDifference: 4.5,
} as const;

export function wait(ms: number) {
  return new Promise<void>((resolve) => window.setTimeout(resolve, ms));
}

export function canStartFaceVerification(inFlight: boolean, lastAttemptAt: number, now: number) {
  return !inFlight && now - lastAttemptAt >= KIOSK_TIMING.recognitionCooldownMs;
}

export function canActivateMicrophone(isSpeaking: boolean, isProcessing: boolean, isListening: boolean) {
  return !isSpeaking && !isProcessing && !isListening;
}
