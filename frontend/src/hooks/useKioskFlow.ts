import { canTransition } from "../runtime/stateMachine";
import { kioskEvents } from "../runtime/eventBus";
import { kioskStream } from "../runtime/stream";
import { RuntimeEvent as Events } from "../runtime/events";
import { useCallback, useEffect, useReducer, useRef } from "react";
import { KIOSK_TIMING } from "../config/kioskRuntime";
import { conversationApi, faceApi, kioskApi, MOCK_FALLBACK_ENABLED } from "../services/apiClient";
import type { CameraStatus, FaceRegistrationFields, FaceVerifyResult, KioskAction, KioskConversation, KioskFlowState, KioskMessage, KioskState, MessageInputMethod, MicStatus } from "../types/kiosk";

const DEVICE_CODE = String(import.meta.env.VITE_KIOSK_DEVICE_CODE ?? "KIOSK_DEV_01");
const FALLBACK_ANSWER = "Máy chủ đang tạm thời không phản hồi. Đây là chế độ thử nghiệm ngoại tuyến; vui lòng khởi động backend để nhận câu trả lời từ hệ thống.";
export function initialState(): KioskFlowState {
  return {
    currentState: "IDLE", session: null, device: { code: DEVICE_CODE }, user: null, conversation: null,
    cameraStatus: "IDLE", micStatus: "IDLE", lastFaceResult: null, messages: [], currentTranscript: "",
    lastAiResponse: null, selectedBookCategory: null, suggestedBooks: [], survey: null, error: null,
    lastActivityAt: Date.now(), isProcessing: false, mockFallbackActive: false,
  };
}

export function reducer(state: KioskFlowState, action: KioskAction): KioskFlowState {
  const active = { lastActivityAt: Date.now() };
  switch (action.type) {
    case "START_SESSION": return { ...initialState(), session: action.session, device: { code: DEVICE_CODE, id: action.session.device_id }, cameraStatus: state.cameraStatus, currentState: "PRESENCE_DETECTED", ...active };
    case "CAMERA_PERMISSION_GRANTED": return { ...state, cameraStatus: "READY",
      currentState: state.currentState === "CAMERA_PERMISSION" ? "IDLE" : state.currentState, error: null, ...active };
    case "CAMERA_PERMISSION_DENIED": return { ...state, cameraStatus: "DENIED", currentState: "CAMERA_PERMISSION", error: action.error ?? null, ...active };
    case "START_FACE_SCAN": return { ...state, currentState: "CAMERA_PREPARING", error: null, ...active };
    case "FACE_VERIFY_SUCCESS": if (!["CAMERA_PREPARING", "FACE_TRACKING", "FACE_RECOGNIZING", "UNKNOWN_FACE", "IDENTITY_CONFIRMING"].includes(state.currentState)) return state; return { ...state, lastFaceResult: action.result, user: action.result.user, currentState: "FACE_RECOGNIZED", isProcessing: false, ...active };
    case "FACE_VERIFY_UNKNOWN": return { ...state, lastFaceResult: action.result, user: null, currentState: "UNKNOWN_FACE", isProcessing: false, ...active };
    case "FACE_VERIFY_FAILED": return { ...state, error: action.error, currentState: "UNKNOWN_FACE", isProcessing: false, ...active };
    case "FACE_ENROLL_SUCCESS": if (state.currentState !== "REGISTER_PROCESSING") return state; return { ...state, lastFaceResult: action.result, user: action.result.user, currentState: "REGISTER_SUCCESS", isProcessing: false, ...active };
    case "START_CONVERSATION": {
      const greeting: KioskMessage = { id: crypto.randomUUID(), role: "assistant", text: state.user
        ? `Xin chào ${state.user.full_name}! Hôm nay tôi có thể giúp gì cho bạn?`
        : "Xin chào bạn, tôi là trợ lý AI thư viện. Bạn cần hỗ trợ gì hôm nay?" };
      return { ...state, conversation: action.conversation, currentState: "AI_GREETING", messages: state.messages.length ? state.messages : [greeting], isProcessing: false, ...active };
    }
    case "USER_MESSAGE_SUBMITTED": return { ...state, messages: [...state.messages, action.message], currentTranscript: action.message.text, currentState: "PROCESSING", isProcessing: true, ...active };
    case "AI_RESPONSE_RECEIVED": return { ...state, messages: [...state.messages, action.message], lastAiResponse: action.message.text, currentState: "AI_SPEAKING", isProcessing: false, mockFallbackActive: state.mockFallbackActive || Boolean(action.mockFallback), ...active };
    case "OPEN_BOOK_SUGGESTIONS": return { ...state, currentState: "BOOK_SUGGESTION", ...active };
    case "OPEN_SURVEY": return { ...state, currentState: "SURVEY", ...active };
    case "SURVEY_SUBMITTED": return { ...state, currentState: "THANK_YOU", ...active };
    case "END_SESSION": return { ...state, isProcessing: false };
    case "RESET_TO_IDLE": return initialState();
    case "SET_ERROR": return { ...state, error: action.error, currentState: "ERROR", isProcessing: false, ...active };
    case "SET_CAMERA_STATUS": return { ...state, cameraStatus: action.status, ...active };
    case "SET_MIC_STATUS": return { ...state, micStatus: action.status };
    case "SET_TRANSCRIPT": return { ...state, currentTranscript: action.transcript, ...active };
    case "SET_BOOK_DATA": return { ...state, selectedBookCategory: action.categoryId, suggestedBooks: action.books, ...active };
    case "SET_SURVEY": return { ...state, survey: action.survey, ...active };
    case "SET_PROCESSING": return { ...state, isProcessing: action.value, ...active };
    case "TOUCH": return { ...state, ...active };
    case "TRANSITION": if (!canTransition(state.currentState, action.state)) return state; return { ...state, currentState: action.state, error: null, ...active };
  }
}

export function useKioskFlow(timeoutSeconds = Number(import.meta.env.VITE_KIOSK_IDLE_TIMEOUT_SECONDS ?? 60)) {
  const [state, dispatch] = useReducer(reducer, undefined, initialState);
  const stateRef = useRef(state);
  const endedSessionRef = useRef<string | null>(null);

  stateRef.current = state;

  const endCurrentSession = useCallback(async (exitReason: string) => {
    const sessionId = stateRef.current.session?.session_id;
    if (!sessionId || endedSessionRef.current === sessionId) return;
    endedSessionRef.current = sessionId;
    try { await kioskApi.endSession(sessionId, exitReason); } catch { /* reset locally even if the backend is unavailable */ }

  }, []);

  const resetToIdle = useCallback(async (exitReason = "USER_EXIT") => {
    epoch.current++;
    turnInFlight.current = false;
    dispatch({ type: "RESET_TO_IDLE" });
    kioskEvents.publish(Events.sessionReset, { reason: exitReason });
    kioskStream.send(Events.sessionReset, { reason: exitReason });
    await endCurrentSession(exitReason);
  }, [endCurrentSession]);

  const sessionStarting = useRef(false);
  const epoch = useRef(0);
  const turnInFlight = useRef(false);
  const startSession = useCallback(async () => {
    if (sessionStarting.current || stateRef.current.currentState !== "IDLE") return false;
    const currentEpoch = epoch.current;
    sessionStarting.current = true;
    endedSessionRef.current = null;
    dispatch({ type: "SET_PROCESSING", value: true });
    try {
      const session = await kioskApi.startSession(DEVICE_CODE);
      if (currentEpoch !== epoch.current) { void kioskApi.endSession(session.session_id, "ABANDONED_START").catch(() => undefined); sessionStarting.current = false; return false; }
      dispatch({ type: "START_SESSION", session });
    } catch (reason) {
      if (currentEpoch !== epoch.current) { sessionStarting.current = false; return false; }
      if (!MOCK_FALLBACK_ENABLED) {
        dispatch({ type: "SET_ERROR", error: reason instanceof Error ? reason.message : "Không thể bắt đầu phiên kiosk." });
        sessionStarting.current = false;
        return false;
      }
      dispatch({ type: "START_SESSION", session: { session_id: crypto.randomUUID(), device_id: "mock-device", status: "active" } });
    }
    sessionStarting.current = false;
    return true;
  }, []);

  const cameraGranted = useCallback(() => dispatch({ type: "CAMERA_PERMISSION_GRANTED" }), []);
  const cameraDenied = useCallback((error?: string) => dispatch({ type: "CAMERA_PERMISSION_DENIED", error }), []);
  const setCameraStatus = useCallback((status: CameraStatus) => dispatch({ type: "SET_CAMERA_STATUS", status }), []);
  const startFaceScan = useCallback(() => dispatch({ type: "START_FACE_SCAN" }), []);

  const enrollFace = useCallback(async (fields: FaceRegistrationFields, imageBlob: Blob) => {
    const currentEpoch = epoch.current;
    dispatch({ type: "SET_PROCESSING", value: true });
    dispatch({ type: "TRANSITION", state: "REGISTER_PROCESSING" });
    try {
      const current = stateRef.current;
      const enrolled = await faceApi.enrollFace({
        sessionId: current.session?.session_id, deviceCode: current.device.code, imageBlob, fields,
      });
      const result: FaceVerifyResult = {
        result: "SUCCESS", user: enrolled.user, confidence_score: enrolled.quality_score, next_state: "WELCOME",
      };
      if (currentEpoch === epoch.current) dispatch({ type: "FACE_ENROLL_SUCCESS", result });
      return enrolled;
    } catch (reason) {
      if (currentEpoch !== epoch.current) throw reason;
      dispatch({ type: "TRANSITION", state: "REGISTER" });
      dispatch({ type: "SET_PROCESSING", value: false });
      throw reason;
    }
  }, []);

  const logEvent = useCallback((event_type: string, content_summary?: string) => {
    const sessionId = stateRef.current.session?.session_id;
    if (sessionId) void kioskApi.logEvent(sessionId, { event_type, content_summary }).catch(() => undefined);
  }, []);
  const startConversation = useCallback(async (): Promise<KioskConversation | null> => {
    const currentEpoch = epoch.current;
    if (stateRef.current.conversation) {
      dispatch({ type: "TRANSITION", state: "VOICE_LISTENING" });
      return stateRef.current.conversation;
    }
    dispatch({ type: "SET_PROCESSING", value: true });
    try {
      const current = stateRef.current;
      const conversation = await conversationApi.startConversation({
        session_id: current.session?.session_id, user_id: current.user?.id,
      });
      if (currentEpoch !== epoch.current) return null;
      dispatch({ type: "START_CONVERSATION", conversation });
      return conversation;
    } catch (reason) {
      if (currentEpoch !== epoch.current) return null;
      if (MOCK_FALLBACK_ENABLED) {
        const conversation = { conversation_id: crypto.randomUUID(), status: "active" };
        dispatch({ type: "START_CONVERSATION", conversation });
        return conversation;
      }
      dispatch({ type: "SET_ERROR", error: reason instanceof Error ? reason.message : "Không thể bắt đầu hội thoại." });
      return null;
    }
  }, []);

  const submitMessage = useCallback(async (text: string, inputMethod: MessageInputMethod = "TEXT", confidence?: number): Promise<string | null> => {
    const clean = text.trim();
    if (!clean || stateRef.current.isProcessing || turnInFlight.current) return null;
    turnInFlight.current = true;
    const currentEpoch = epoch.current;
    const conversation = stateRef.current.conversation ?? await startConversation();
    if (!conversation) { turnInFlight.current = false; return null; }
    dispatch({ type: "USER_MESSAGE_SUBMITTED", message: { id: crypto.randomUUID(), role: "user", text: clean, inputMethod } });
    try {
      const current = stateRef.current;
      const result = await kioskStream.request({
        conversation_id: conversation.conversation_id, session_id: current.session?.session_id,
        message_text: clean, input_method: inputMethod, confidence_score: confidence,
      });
      if (currentEpoch !== epoch.current) return null;
      dispatch({ type: "AI_RESPONSE_RECEIVED", message: { id: crypto.randomUUID(), role: "assistant", text: String(result.answer) }, mockFallback: result.provider === "mock" });
      return String(result.answer);
    } catch (reason) {
      if (currentEpoch !== epoch.current) return null;
      if (MOCK_FALLBACK_ENABLED) {
        dispatch({ type: "AI_RESPONSE_RECEIVED", message: { id: crypto.randomUUID(), role: "assistant", text: FALLBACK_ANSWER }, mockFallback: true });
        return FALLBACK_ANSWER;
      }
      dispatch({ type: "SET_ERROR", error: reason instanceof Error ? reason.message : "Không thể nhận câu trả lời từ AI." });
      return null;
    }
    finally { if (currentEpoch === epoch.current) turnInFlight.current = false; }
  }, [startConversation]);

  const setMicStatus = useCallback((status: MicStatus) => dispatch({ type: "SET_MIC_STATUS", status }), []);
  const openBooks = useCallback(() => { logEvent("BOOK_SUGGESTIONS_OPENED"); dispatch({ type: "OPEN_BOOK_SUGGESTIONS" }); }, [logEvent]);
  const openSurvey = useCallback(() => { logEvent("SURVEY_OPENED"); dispatch({ type: "OPEN_SURVEY" }); }, [logEvent]);
  const completeSurvey = useCallback(() => dispatch({ type: "SURVEY_SUBMITTED" }), []);
  const transitionTo = useCallback((next: KioskState) => dispatch({ type: "TRANSITION", state: next }), []);
  const touch = useCallback(() => dispatch({ type: "TOUCH" }), []);

  useEffect(() => {
    if (["PRESENCE_DETECTED", "WAKE_UP", "GREETING"].includes(state.currentState)) {
      const next: KioskState = state.currentState === "PRESENCE_DETECTED" ? "WAKE_UP" : state.currentState === "WAKE_UP" ? "GREETING" : "CAMERA_PREPARING";
      const id = window.setTimeout(() => dispatch({ type: "TRANSITION", state: next }), state.currentState === "GREETING" ? 800 : 150);
      return () => window.clearTimeout(id);
    }
    if (state.currentState === "FACE_RECOGNIZED" || state.currentState === "STOP_CAMERA") {
      const id = window.setTimeout(() => dispatch({ type: "TRANSITION", state: state.currentState === "FACE_RECOGNIZED" ? "STOP_CAMERA" : "WELCOME" }), 100);
      return () => window.clearTimeout(id);
    }
    if (state.currentState === "REGISTER_SUCCESS") {
      const id = window.setTimeout(() => dispatch({ type: "TRANSITION", state: "WELCOME" }), KIOSK_TIMING.registrationSuccessMs);
      return () => window.clearTimeout(id);
    }
    if (state.currentState === "THANK_YOU") {
      const id = window.setTimeout(() => dispatch({ type: "TRANSITION", state: "RETURN_IDLE" }), KIOSK_TIMING.thankYouMs);
      return () => window.clearTimeout(id);
    }
    if (state.currentState === "RETURN_IDLE") {
      const id = window.setTimeout(() => { void resetToIdle("COMPLETED"); }, KIOSK_TIMING.returnIdleMs);
      return () => window.clearTimeout(id);
    }
  }, [state.currentState, resetToIdle]);

  useEffect(() => {
    if (state.currentState === "IDLE" || state.isProcessing || state.micStatus === "PROCESSING") return;
    const elapsed = Date.now() - state.lastActivityAt;
    const id = window.setTimeout(() => { void resetToIdle("TIMEOUT"); }, Math.max(0, timeoutSeconds * 1000 - elapsed));
    return () => window.clearTimeout(id);
  }, [state.currentState, state.isProcessing, state.lastActivityAt, state.micStatus, timeoutSeconds, resetToIdle]);

  useEffect(() => {
    const onActivity = () => dispatch({ type: "TOUCH" });
    window.addEventListener("pointerdown", onActivity); window.addEventListener("keydown", onActivity);
    return () => { window.removeEventListener("pointerdown", onActivity); window.removeEventListener("keydown", onActivity); };
  }, []);

  useEffect(() => {
    const events: Partial<Record<KioskState, string>> = { WELCOME: "welcome_started", SURVEY: "survey_started", THANK_YOU: "survey_completed", IDLE: Events.sessionReset };
    const event = events[state.currentState];
    if (event) { kioskEvents.publish(event); kioskStream.send(event); }
  }, [state.currentState]);

  return { ...state, dispatch, startSession, cameraGranted, cameraDenied, setCameraStatus, startFaceScan,
    enrollFace, startConversation, submitMessage, setMicStatus, openBooks, openSurvey,
    completeSurvey, transitionTo, touch, resetToIdle };
}
