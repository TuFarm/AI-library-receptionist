import { useEffect, useRef, useState } from "react";
import type { useCamera } from "../hooks/useCamera";
import type { useKioskFlow } from "../hooks/useKioskFlow";
import type { FaceVerifyResult } from "../types/kiosk";
import { kioskEvents } from "./eventBus";
import { RuntimeEvent as Events } from "./events";
import { kioskStream } from "./stream";

const sensingStates = new Set(["CAMERA_PREPARING", "FACE_TRACKING", "FACE_RECOGNIZING", "UNKNOWN_FACE", "REGISTER"]);
export function useRealtimeSensor(flow: ReturnType<typeof useKioskFlow>, camera: ReturnType<typeof useCamera>) {
  const current = useRef({ flow, camera }); current.current = { flow, camera };
  const [guidance, setGuidance] = useState("Vui lòng nhìn vào camera");
  const [qualityReady, setQualityReady] = useState(false);
  const [diagnostics, setDiagnostics] = useState<Record<string, unknown>>({});
  const [frozenFrameUrl, setFrozenFrameUrl] = useState<string | null>(null);
  const starting = useRef(false);
  const sentFrame = useRef<Blob | null>(null);
  const enrollmentFrame = useRef<{ blob: Blob; at: number } | null>(null);
  const frozenUrlRef = useRef<string | null>(null);
  const state = flow.currentState;
  const sensing = sensingStates.has(state);
  const registration = state === "REGISTER" || state === "REGISTER_PROCESSING";
  const externalPresence = Boolean(window.kiosk?.onPresence);
  const idleCamera = false;

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
      if (event === Events.registrationRequested && f.currentState === "UNKNOWN_FACE") f.transitionTo("REGISTER");
      if (event === Events.identityUnknown && f.currentState === "REGISTER") f.transitionTo("UNKNOWN_FACE");
      if (event === Events.faceDetected || event === Events.presenceDetected) { window.clearTimeout(absenceTimer); absenceTimer = undefined; }
      if (event === Events.presenceLost && absenceTimer === undefined && ["CAMERA_PREPARING", "FACE_TRACKING", "FACE_RECOGNIZING", "UNKNOWN_FACE"].includes(f.currentState)) {
        absenceTimer = window.setTimeout(() => {
          if (["CAMERA_PREPARING", "FACE_TRACKING", "FACE_RECOGNIZING", "UNKNOWN_FACE"].includes(current.current.flow.currentState)) void current.current.flow.resetToIdle("PRESENCE_LOST");
          absenceTimer = undefined;
        }, 8000);
      }
      if (event === Events.faceQualityGood && sentFrame.current) enrollmentFrame.current = { blob: sentFrame.current, at: performance.now() };
      if (event === Events.identityCandidate && payload.confirmed === true && sensingStates.has(f.currentState) && f.currentState !== "REGISTER" && payload.session_id === f.session?.session_id) {
        if (sentFrame.current) {
          if (frozenUrlRef.current) URL.revokeObjectURL(frozenUrlRef.current);
          frozenUrlRef.current = URL.createObjectURL(sentFrame.current);
          setFrozenFrameUrl(frozenUrlRef.current);
        }
        c.stopCamera();
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
        const faces = payload.faces as { quality_ok: boolean; guidance: string | null }[];
        setQualityReady(faces.length === 1 && faces[0].quality_ok);
        if (faces.length !== 1 || !faces[0].quality_ok) enrollmentFrame.current = null;
        setGuidance(faces[0]?.guidance ?? (faces.length ? "Đang nhận diện…" : "Vui lòng nhìn vào camera"));
        setDiagnostics(d => ({ ...d, faces, vision: payload.metrics }));
      }
      if (event === Events.pong && import.meta.env.DEV && import.meta.env.VITE_ENABLE_DEV_CONTROLS === "true") void window.kiosk?.getDiagnostics?.().then(electron => setDiagnostics(d => ({ ...d, electron })));
      if ([Events.frameReady, Events.recognitionProgress, Events.recognitionFinished, Events.transportLatency].includes(event as never)) setDiagnostics(d => ({ ...d, [event]: payload }));
      if (event === Events.identityConfirmed && (sensingStates.has(f.currentState) || f.currentState === "IDENTITY_CONFIRMING") && f.currentState !== "REGISTER") {
        // Stop physical tracks before publishing the UI identity transition.
        c.stopCamera();
        kioskStream.configure({ mode: "conversation", session_id: f.session?.session_id });
        f.dispatch({ type: "FACE_VERIFY_SUCCESS", result: payload as FaceVerifyResult });
      }
      if (event === Events.streamError || event === Events.streamDisconnected) {
        enrollmentFrame.current = null;
        setQualityReady(false);
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
      unsubscribe(); stopPresence?.(); window.clearTimeout(presenceTimer); window.clearTimeout(absenceTimer); kioskStream.close();
      if (frozenUrlRef.current) URL.revokeObjectURL(frozenUrlRef.current);
    };
  }, []);

  useEffect(() => {
    if (state !== "IDENTITY_CONFIRMING") return;
    const timer = window.setTimeout(() => current.current.flow.dispatch({ type: "SET_ERROR", error: "Xác nhận quá thời gian chờ." }), 10000);
    return () => window.clearTimeout(timer);
  }, [state]);
  useEffect(() => {
    enrollmentFrame.current = null;
    setQualityReady(false);
    kioskStream.configure({ mode: registration ? "registration" : sensing ? "recognition" : state === "IDLE" ? "idle" : "conversation", session_id: flow.session?.session_id });
  }, [registration, sensing, state === "IDLE", flow.session?.session_id]);

  useEffect(() => {
    if (!sensing && !idleCamera) { sentFrame.current = null; enrollmentFrame.current = null; camera.stopCamera(); return; }
    let active = true;
    let timer: number;
    let frames = 0; const started = performance.now();
    const sample = async () => {
      if (!active) return;
      try {
        if (kioskStream.frameReady) {
          const blob = await camera.captureFrame();
          if (active && kioskStream.frame(blob)) { sentFrame.current = blob; frames++; setDiagnostics(d => ({ ...d, fps: frames * 1000 / (performance.now()-started) })); }
        }
      } catch { /* Track loss is reported by the camera adapter; never queue frames. */ }
      if (active) timer = window.setTimeout(sample, idleCamera ? 750 : 33);
    };
    void camera.requestCamera().then(ok => {
      if (!active) return;
      if (ok) { kioskEvents.publish(Events.cameraReady); kioskStream.send(Events.cameraReady); void sample(); }
      else { setGuidance("Camera chưa sẵn sàng. Vui lòng kiểm tra quyền truy cập."); timer = window.setTimeout(() => { if (active) void camera.requestCamera().then(ready => { if (active && ready) void sample(); }); }, 1500); }
    });
    return () => { active = false; sentFrame.current = null; enrollmentFrame.current = null; window.clearTimeout(timer); camera.stopCamera(); kioskEvents.publish(Events.cameraStopped); };
  }, [sensing, idleCamera, camera.requestCamera, camera.stopCamera, camera.captureFrame]);

  useEffect(() => {
    if (!sensing || registration) return;
    const timer = window.setTimeout(() => {
      kioskEvents.publish(Events.identityUnknown); current.current.flow.transitionTo("UNKNOWN_FACE");
    }, 20000);
    return () => window.clearTimeout(timer);
  }, [sensing, registration]);
  const captureEnrollmentFrame = async () => {
    const frame = enrollmentFrame.current;
    if (!frame || performance.now()-frame.at > 2000) throw new Error("Vui lòng nhìn vào camera và giữ yên.");
    return frame.blob;
  };
  return { guidance, qualityReady, diagnostics, sensing, externalPresence, captureEnrollmentFrame, frozenFrameUrl };
}
