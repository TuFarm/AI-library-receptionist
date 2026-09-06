import { describe, expect, it } from "vitest";
import { canActivateMicrophone, canStartFaceVerification, KIOSK_TIMING } from "./kioskRuntime";
import { hasLiveVideoTrack, isVideoFrameReady } from "./cameraRuntime";
import { initialState, reducer } from "../hooks/useKioskFlow";

describe("production kiosk state machine", () => {
  it("starts idle and enters the presence flow without a button", () => {
    const idle = initialState();
    expect(idle.currentState).toBe("IDLE");
    const detected = reducer(idle, { type: "START_SESSION", session: { session_id: "session-1", status: "active" } });
    expect(detected.currentState).toBe("PRESENCE_DETECTED");
    expect(reducer(detected, { type: "START_FACE_SCAN" }).currentState).toBe("CAMERA_PREPARING");
  });

  it("routes successful, unknown and registered faces to their dedicated experiences", () => {
    const base = { ...initialState(), currentState: "FACE_TRACKING" as const };
    const success = { result: "SUCCESS", user: { id: "u1", student_code: "001", full_name: "Nguyễn Văn An" }, confidence_score: .94, next_state: "WELCOME" as const };
    const unknown = { result: "UNKNOWN_FACE", user: null, confidence_score: .2, next_state: "FACE_UNKNOWN" as const };
    expect(reducer(base, { type: "FACE_VERIFY_SUCCESS", result: success }).currentState).toBe("FACE_RECOGNIZED");
    expect(reducer(base, { type: "FACE_VERIFY_UNKNOWN", result: unknown }).currentState).toBe("UNKNOWN_FACE");
    expect(reducer({ ...base, currentState: "REGISTER_PROCESSING" }, { type: "FACE_ENROLL_SUCCESS", result: success }).currentState).toBe("REGISTER_SUCCESS");
  });

  it("prevents duplicate verification during a request and during cooldown", () => {
    expect(canStartFaceVerification(true, 0, 5000)).toBe(false);
    expect(canStartFaceVerification(false, 4000, 5000)).toBe(false);
    expect(canStartFaceVerification(false, 2000, 5000)).toBe(true);
  });

  it("opens the microphone only after TTS and processing are finished", () => {
    expect(canActivateMicrophone(true, false, false)).toBe(false);
    expect(canActivateMicrophone(false, true, false)).toBe(false);
    expect(canActivateMicrophone(false, false, true)).toBe(false);
    expect(canActivateMicrophone(false, false, false)).toBe(true);
    expect(KIOSK_TIMING.postSpeechSilenceMs).toBe(500);
  });

  it("uses the required timing safeguards", () => {
    expect(KIOSK_TIMING.presenceConfirmationMs).toBe(1200);
    expect(KIOSK_TIMING.welcomeDisplayMs).toBe(2500);
    expect(KIOSK_TIMING.thankYouMs).toBe(3000);
  });

  it("does not lose camera readiness when a preview element changes", () => {
    const liveStream = { getVideoTracks: () => [{ readyState: "live" }] } as unknown as MediaStream;
    const stoppedStream = { getVideoTracks: () => [{ readyState: "ended" }] } as unknown as MediaStream;
    expect(hasLiveVideoTrack(liveStream)).toBe(true);
    expect(hasLiveVideoTrack(stoppedStream)).toBe(false);
    expect(isVideoFrameReady({ readyState: 4, videoWidth: 1280, videoHeight: 720 } as HTMLVideoElement)).toBe(true);
    expect(isVideoFrameReady(null)).toBe(false);
  });

  it("preserves an active scan state when camera reconnects", () => {
    const preparing = { ...initialState(), currentState: "CAMERA_PREPARING" as const };
    expect(reducer(preparing, { type: "CAMERA_PERMISSION_GRANTED" }).currentState).toBe("CAMERA_PREPARING");
    const permission = { ...initialState(), currentState: "CAMERA_PERMISSION" as const };
    expect(reducer(permission, { type: "CAMERA_PERMISSION_GRANTED" }).currentState).toBe("IDLE");
  });
});
