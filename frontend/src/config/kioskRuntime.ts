export const KIOSK_TIMING = {
  presenceConfirmationMs: 1200,
  presenceSampleMs: 200,
  cameraPreparationMs: 1000,
  faceStableMs: 1200,
  faceSampleMs: 160,
  countdownStepMs: 500,
  minimumVerificationMs: 1000,
  recognitionCooldownMs: 2000,
  welcomeDisplayMs: 2500,
  postSpeechSilenceMs: 500,
  registrationSuccessMs: 2200,
  thankYouMs: 3000,
  returnIdleMs: 500,
  transitionMs: 420,
} as const;

export const KIOSK_MOTION = {
  presenceDifference: 7,
  minimumContrast: 15,
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
