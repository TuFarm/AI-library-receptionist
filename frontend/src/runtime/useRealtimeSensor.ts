import { useEffect, useRef, useState } from "react";
import type { useCamera } from "../hooks/useCamera";
import type { useKioskFlow } from "../hooks/useKioskFlow";
import type { FaceVerifyResult } from "../types/kiosk";
import { kioskEvents } from "./eventBus";
import { RuntimeEvent as Events } from "./events";
import { kioskStream } from "./stream";
import { KIOSK_ENROLLMENT, KIOSK_RECOGNITION } from "../config/kioskRuntime";
import { EnrollmentEvidenceGuard } from "./enrollmentEvidence";
import { UnknownRecognitionGuard, type UnknownRecognitionContext } from "./recognitionUnknown";

const sensingStates = new Set(["CAMERA_PREPARING", "FACE_TRACKING", "FACE_RECOGNIZING", "UNKNOWN_FACE", "REGISTER"]);
export function useRealtimeSensor(flow: ReturnType<typeof useKioskFlow>, camera: ReturnType<typeof useCamera>) {
  const current = useRef({ flow, camera }); current.current = { flow, camera };
  const [guidance, setGuidance] = useState("Vui lòng nhìn vào camera");
  const [qualityReady, setQualityReady] = useState(false);
  const [faceCount, setFaceCount] = useState(0);
  const [multipleFacesDetected, setMultipleFacesDetected] = useState(false);
  const [captureGeneration, setCaptureGeneration] = useState(0);
  const [capturePrepared, setCapturePrepared] = useState(false);
  const [captureCountdown, setCaptureCountdown] = useState(3);
  const [frozenFrameUrl, setFrozenFrameUrl] = useState<string | null>(null);
  const starting = useRef(false);
  const sentFrame = useRef<Blob | null>(null);
  const enrollmentEvidence = useRef(new EnrollmentEvidenceGuard());
  const unknownRecognition = useRef(new UnknownRecognitionGuard(KIOSK_RECOGNITION.unknownMinMs, KIOSK_RECOGNITION.unknownAttempts));
  const unknownTimer = useRef<number | undefined>(undefined);
  const identityPendingRef = useRef(false);
  const confirmationSessionRef = useRef<string | null>(null);
  const captureActiveRef = useRef(false);
  const captureGenerationRef = useRef(0);
  const captureStartedAtRef = useRef<number | null>(null);
  const faceCountRef = useRef(0);
  const qualityReadyRef = useRef(false);
  const multipleFacesDetectedRef = useRef(false);
  const trackIdRef = useRef<number | null>(null);
  const frozenUrlRef = useRef<string | null>(null);
  const state = flow.currentState;
  const sensing = sensingStates.has(state);
  const registration = state === "REGISTER" || state === "REGISTER_PROCESSING";
  const externalPresence = Boolean(window.kiosk?.onPresence);
  const idleCamera = false;

  const resetUnknownRecognition = () => {
    window.clearTimeout(unknownTimer.current);
    unknownTimer.current = undefined;
    identityPendingRef.current = false;
    unknownRecognition.current.reset();
  };
  const updateQualityReady = (ready: boolean) => {
    qualityReadyRef.current = ready;
    setQualityReady(ready);
  };

  const recognitionContext = (f: ReturnType<typeof useKioskFlow>): UnknownRecognitionContext => ({
    sessionId: f.session?.session_id,
    trackId: trackIdRef.current,
    faceCount: faceCountRef.current,
    qualityReady: qualityReadyRef.current,
    recognitionActive: ["CAMERA_PREPARING", "FACE_TRACKING", "FACE_RECOGNIZING"].includes(f.currentState),
    identityPending: identityPendingRef.current || f.currentState === "IDENTITY_CONFIRMING",
  });

  const restartEnrollmentCapture = () => {
    const f = current.current.flow;
    if (!captureActiveRef.current || f.currentState !== "REGISTER") return;
    sentFrame.current = null;
    faceCountRef.current = 0;
    trackIdRef.current = null;
    updateQualityReady(false);
    setFaceCount(0);
    setCapturePrepared(false);
    setCaptureCountdown(3);
    const now = performance.now();
    captureStartedAtRef.current = now;
    captureGenerationRef.current = enrollmentEvidence.current.beginCapture(f.session?.session_id, now);
    setCaptureGeneration(captureGenerationRef.current);
    kioskStream.configure({ mode: "registration", session_id: f.session?.session_id,
      capture_generation: captureGenerationRef.current });
  };

  const beginEnrollmentCapture = () => {
    captureActiveRef.current = true;
    multipleFacesDetectedRef.current = false;
    setMultipleFacesDetected(false);
    restartEnrollmentCapture();
  };

  const endEnrollmentCapture = () => {
    captureActiveRef.current = false;
    captureStartedAtRef.current = null;
    sentFrame.current = null;
    enrollmentEvidence.current.endCapture();
    captureGenerationRef.current = enrollmentEvidence.current.currentGeneration();
    setCaptureGeneration(captureGenerationRef.current);
    setCapturePrepared(false);
    setCaptureCountdown(3);
    updateQualityReady(false);
  };

  useEffect(() => {
    if (state === "IDLE" && frozenUrlRef.current) {
      URL.revokeObjectURL(frozenUrlRef.current);
      frozenUrlRef.current = null;
      setFrozenFrameUrl(null);
    }
  }, [state]);

  useEffect(() => {
    let absenceTimer: number | undefined;
    const unsubscribe = kioskEvents.subscribe(({ event, payload }) => {
      const { flow: f, camera: c } = current.current;
      if (event === Events.registrationRequested && f.currentState === "UNKNOWN_FACE") {
        resetUnknownRecognition();
        f.transitionTo("REGISTER");
      }
      if (event === Events.faceDetected || event === Events.presenceDetected) { window.clearTimeout(absenceTimer); absenceTimer = undefined; }
      if (event === Events.presenceLost && absenceTimer === undefined && ["CAMERA_PREPARING", "FACE_TRACKING", "FACE_RECOGNIZING", "UNKNOWN_FACE"].includes(f.currentState)) {
        absenceTimer = window.setTimeout(() => {
          if (["CAMERA_PREPARING", "FACE_TRACKING", "FACE_RECOGNIZING", "UNKNOWN_FACE"].includes(current.current.flow.currentState)) void current.current.flow.resetToIdle("PRESENCE_LOST");
          absenceTimer = undefined;
        }, 8000);
      }
      if (event === Events.sessionState && captureActiveRef.current && payload.mode === "registration" &&
          payload.session_id === f.session?.session_id && Number(payload.capture_generation) === captureGenerationRef.current) {
        enrollmentEvidence.current.acknowledge(captureGenerationRef.current, f.session?.session_id);
      }
      if (event === Events.faceQualityGood && f.currentState === "REGISTER" && captureActiveRef.current && sentFrame.current &&
          payload.session_id === f.session?.session_id && faceCountRef.current === 1 && trackIdRef.current === Number(payload.track_id)) {
        const accepted = enrollmentEvidence.current.accept(sentFrame.current, {
          sessionId: String(payload.session_id), trackId: Number(payload.track_id), now: performance.now(),
          generation: captureGenerationRef.current, faceCount: faceCountRef.current,
          multipleFacesDetected: false, qualityReady: true,
          stableFrames: Number(payload.stable_frames), stableMs: Number(payload.stable_ms),
          requiredStableFrames: KIOSK_ENROLLMENT.stableFrames, requiredStableMs: KIOSK_ENROLLMENT.stableMs,
        });
        updateQualityReady(accepted);
      } else if (event === Events.faceQualityGood && f.currentState !== "REGISTER" &&
          ["CAMERA_PREPARING", "FACE_TRACKING", "FACE_RECOGNIZING"].includes(f.currentState) &&
          faceCountRef.current === 1 && trackIdRef.current === Number(payload.track_id)) {
        updateQualityReady(true);
      }
      if (event === Events.multipleFacesDetected && f.currentState === "REGISTER" && payload.session_id === f.session?.session_id) {
        const wasMultiple = multipleFacesDetectedRef.current;
        enrollmentEvidence.current.invalidateEvidence();
        sentFrame.current = null;
        trackIdRef.current = null;
        faceCountRef.current = Number(payload.face_count) || 2;
        setFaceCount(faceCountRef.current);
        multipleFacesDetectedRef.current = true;
        setMultipleFacesDetected(true);
        updateQualityReady(false);
        setGuidance(String(payload.guidance));
        if (captureActiveRef.current && !wasMultiple) restartEnrollmentCapture();
      }
      if (event === Events.identityCandidate && f.currentState !== "REGISTER" &&
          payload.session_id === f.session?.session_id && Number(payload.track_id) === trackIdRef.current) {
        identityPendingRef.current = true;
        unknownRecognition.current.markCandidate(f.session?.session_id, trackIdRef.current);
        window.clearTimeout(unknownTimer.current);
      }
      if (event === Events.identityCandidate && payload.confirmed === true && sensingStates.has(f.currentState) && f.currentState !== "REGISTER" && payload.session_id === f.session?.session_id) {
        if (sentFrame.current) {
          if (frozenUrlRef.current) URL.revokeObjectURL(frozenUrlRef.current);
          frozenUrlRef.current = URL.createObjectURL(sentFrame.current);
          setFrozenFrameUrl(frozenUrlRef.current);
        }
        c.stopCamera();
        confirmationSessionRef.current = f.session?.session_id ?? null;
        kioskStream.send("confirm_identity", { session_id: f.session?.session_id });
        f.transitionTo("IDENTITY_CONFIRMING");
      }
      if (event === Events.presenceDetected && f.currentState === "IDLE" && !starting.current) {
        starting.current = true;
        void f.startSession().finally(() => { starting.current = false; });
      }
      if (event === Events.recognitionStarted && ["CAMERA_PREPARING", "FACE_TRACKING"].includes(f.currentState)) f.transitionTo("FACE_RECOGNIZING");
      if (event === Events.faceTracking) {
        if (["CAMERA_PREPARING", "FACE_RECOGNIZING"].includes(f.currentState)) f.transitionTo("FACE_TRACKING");
        const faces = payload.faces as { track_id: number; quality_ok: boolean; guidance: string | null }[];
        const wasMultiple = multipleFacesDetectedRef.current;
        const nextTrackId = faces.length === 1 ? faces[0].track_id : null;
        if (trackIdRef.current !== nextTrackId) {
          enrollmentEvidence.current.invalidateEvidence();
          resetUnknownRecognition();
          updateQualityReady(false);
        }
        trackIdRef.current = nextTrackId;
        faceCountRef.current = faces.length;
        setFaceCount(faces.length);
        if (faces.length !== 1 || !faces[0].quality_ok) {
          enrollmentEvidence.current.invalidateEvidence();
          resetUnknownRecognition();
          if (faces.length !== 1) sentFrame.current = null;
          updateQualityReady(false);
        }
        multipleFacesDetectedRef.current = faces.length >= 2;
        setMultipleFacesDetected(multipleFacesDetectedRef.current);
        setGuidance(faces.length >= 2 ? "Phát hiện nhiều khuôn mặt. Vui lòng chỉ để một người xuất hiện trong khung hình."
          : faces[0]?.guidance ?? (faces.length ? "Đang kiểm tra độ ổn định…" : "Vui lòng đưa khuôn mặt vào camera"));
        if (captureActiveRef.current && wasMultiple && faces.length === 1) restartEnrollmentCapture();
      }
      if (event === Events.recognitionFinished && payload.session_id === f.session?.session_id &&
          ["CAMERA_PREPARING", "FACE_TRACKING", "FACE_RECOGNIZING"].includes(f.currentState)) {
        const now = performance.now();
        identityPendingRef.current = false;
        const context = recognitionContext(f);
        const ready = unknownRecognition.current.observe(payload.result, context, now);
        const declareUnknown = () => {
          const activeFlow = current.current.flow;
          if (!unknownRecognition.current.isReady(recognitionContext(activeFlow), performance.now())) return;
          resetUnknownRecognition();
          kioskEvents.publish(Events.identityUnknown, { session_id: activeFlow.session?.session_id });
          activeFlow.transitionTo("UNKNOWN_FACE");
        };
        if (ready) declareUnknown();
        else {
          const delay = unknownRecognition.current.delayUntilEligible(now);
          window.clearTimeout(unknownTimer.current);
          if (delay !== null) unknownTimer.current = window.setTimeout(declareUnknown, delay);
        }
      }
      if (event === Events.identityConfirmed && f.currentState === "IDENTITY_CONFIRMING" &&
          confirmationSessionRef.current === f.session?.session_id &&
          payload.session_id === confirmationSessionRef.current) {
        // Stop physical tracks before publishing the UI identity transition.
        resetUnknownRecognition();
        confirmationSessionRef.current = null;
        c.stopCamera();
        kioskStream.configure({ mode: "conversation", session_id: f.session?.session_id });
        f.dispatch({ type: "FACE_VERIFY_SUCCESS", result: payload as FaceVerifyResult });
      }
      if (event === Events.streamError || event === Events.streamDisconnected) {
        resetUnknownRecognition();
        confirmationSessionRef.current = null;
        if (captureActiveRef.current) restartEnrollmentCapture();
        else enrollmentEvidence.current.endCapture();
        updateQualityReady(false);
        setGuidance(event === Events.streamError ? String(payload.message) : "Đang kết nối lại với trợ lý…");
        if (f.currentState === "IDENTITY_CONFIRMING") f.dispatch({ type: "SET_ERROR", error: "Xác nhận bị gián đoạn. Vui lòng bắt đầu phiên mới." });
      }
    });
    kioskStream.connect();
    let presenceTimer: number | undefined;
    const stopPresence = window.kiosk?.onPresence?.((present) => {
      window.clearTimeout(presenceTimer);
      if (present) presenceTimer = window.setTimeout(() => kioskEvents.publish(Events.presenceDetected), 1200);
      else kioskEvents.publish(Events.presenceLost);
    });
    return () => {
      unsubscribe(); stopPresence?.(); window.clearTimeout(presenceTimer); window.clearTimeout(absenceTimer);
      window.clearTimeout(unknownTimer.current); kioskStream.close();
      if (frozenUrlRef.current) URL.revokeObjectURL(frozenUrlRef.current);
    };
  }, []);

  useEffect(() => {
    if (state !== "IDENTITY_CONFIRMING") return;
    const timer = window.setTimeout(() => current.current.flow.dispatch({ type: "SET_ERROR", error: "Xác nhận quá thời gian chờ." }), 10000);
    return () => window.clearTimeout(timer);
  }, [state]);
  useEffect(() => {
    resetUnknownRecognition();
    if (state !== "IDENTITY_CONFIRMING") confirmationSessionRef.current = null;
    enrollmentEvidence.current.endCapture();
    captureActiveRef.current = false;
    captureStartedAtRef.current = null;
    captureGenerationRef.current = enrollmentEvidence.current.currentGeneration();
    faceCountRef.current = 0;
    multipleFacesDetectedRef.current = false;
    trackIdRef.current = null;
    setFaceCount(0);
    setMultipleFacesDetected(false);
    updateQualityReady(false);
    const mode = registration ? "registration" : (sensing || state === "IDENTITY_CONFIRMING") ? "recognition" : state === "IDLE" ? "idle" : "conversation";
    kioskStream.configure({ mode, session_id: flow.session?.session_id });
  }, [registration, sensing, state === "IDLE", flow.session?.session_id]);

  useEffect(() => {
    if (!sensing && !idleCamera) { sentFrame.current = null; enrollmentEvidence.current.invalidateEvidence(); camera.stopCamera(); return; }
    let active = true;
    let timer: number;
    const sample = async () => {
      if (!active) return;
      try {
        if (kioskStream.frameReady) {
          const blob = await camera.captureFrame();
          if (active && kioskStream.frame(blob)) {
            sentFrame.current = blob;
          }
        }
      } catch { /* Track loss is reported by the camera adapter; never queue frames. */ }
      if (active) timer = window.setTimeout(sample, idleCamera ? 750 : 33);
    };
    void camera.requestCamera().then(ok => {
      if (!active) return;
      if (ok) { kioskEvents.publish(Events.cameraReady); kioskStream.send(Events.cameraReady); void sample(); }
      else { setGuidance("Camera chưa sẵn sàng. Vui lòng kiểm tra quyền truy cập."); timer = window.setTimeout(() => { if (active) void camera.requestCamera().then(ready => { if (active && ready) void sample(); }); }, 1500); }
    });
    return () => { active = false; sentFrame.current = null; enrollmentEvidence.current.invalidateEvidence(); window.clearTimeout(timer); camera.stopCamera(); kioskEvents.publish(Events.cameraStopped); };
  }, [sensing, idleCamera, camera.requestCamera, camera.stopCamera, camera.captureFrame]);

  useEffect(() => {
    if (!captureActiveRef.current || state !== "REGISTER" || captureStartedAtRef.current === null) return;
    const updatePreparation = () => {
      const elapsed = performance.now() - captureStartedAtRef.current!;
      const remaining = Math.max(0, KIOSK_ENROLLMENT.capturePreparationMs - elapsed);
      setCaptureCountdown(Math.max(1, Math.ceil(remaining / (KIOSK_ENROLLMENT.capturePreparationMs / 3))));
      setCapturePrepared(remaining === 0);
    };
    updatePreparation();
    const timer = window.setInterval(updatePreparation, 100);
    return () => window.clearInterval(timer);
  }, [captureGeneration, state]);

  const captureEnrollmentFrame = async () => {
    return enrollmentEvidence.current.capture(
      current.current.flow.session?.session_id,
      captureGenerationRef.current,
      KIOSK_ENROLLMENT.capturePreparationMs,
      faceCountRef.current,
      trackIdRef.current,
      multipleFacesDetectedRef.current,
      performance.now(),
    );
  };
  return { guidance, qualityReady, faceCount, multipleFacesDetected, sensing, externalPresence,
    captureEnrollmentFrame, beginEnrollmentCapture, endEnrollmentCapture, captureGeneration, capturePrepared,
    captureCountdown, frozenFrameUrl };
}
