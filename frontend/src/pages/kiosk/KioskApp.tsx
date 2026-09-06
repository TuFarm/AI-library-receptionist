import { kioskStream } from "../../runtime/stream";
import { AssistantAvatar } from "../../components/kiosk/AssistantAvatar";
import { CameraPreview } from "../../components/kiosk/CameraPreview";
import { KioskChrome } from "../../components/kiosk/KioskChrome";
import { useCamera } from "../../hooks/useCamera";
import { useKioskFlow } from "../../hooks/useKioskFlow";
import { useRealtimeSensor } from "../../runtime/useRealtimeSensor";
import FaceRegistrationScreen from "./FaceRegistrationScreen";
import KioskSurveyScreen from "./KioskSurveyScreen";
import KioskThankYouScreen from "./KioskThankYouScreen";
import KioskVoiceChatScreen from "./KioskVoiceChatScreen";
import WelcomeScreen from "./WelcomeScreen";
import { kioskEvents } from "../../runtime/eventBus";
import { RuntimeEvent as Events } from "../../runtime/events";

const VOICE = new Set(["AI_GREETING", "VOICE_LISTENING", "USER_SPEAKING", "PROCESSING", "AI_SPEAKING", "LISTENING"]);
const RECOGNITION = new Set(["CAMERA_PREPARING", "FACE_TRACKING", "FACE_RECOGNIZING", "UNKNOWN_FACE"]);
export default function KioskApp() {
  const flow = useKioskFlow();
  const camera = useCamera();
  const sensor = useRealtimeSensor(flow, camera);
  const state = flow.currentState;
  let content;
  if (VOICE.has(state)) content = <KioskVoiceChatScreen flow={flow}/>;
  else if (state === "REGISTER" || state === "REGISTER_PROCESSING") content = <FaceRegistrationScreen videoRef={camera.videoRef} cameraStatus={camera.cameraStatus}
    cameraError={camera.error} busy={flow.isProcessing} captureFrame={sensor.captureEnrollmentFrame} qualityReady={sensor.qualityReady} onEnroll={flow.enrollFace}
    onCancel={() => kioskEvents.publish(Events.identityUnknown)}/>;
  else if (state === "WELCOME") content = <WelcomeScreen user={flow.user} frozenFrameUrl={sensor.frozenFrameUrl} onContinue={() => void flow.startConversation()}/>;
  else if (state === "SURVEY") content = <KioskSurveyScreen sessionId={flow.session?.session_id} userId={flow.user?.id} onComplete={flow.completeSurvey}/>;
  else if (state === "THANK_YOU") content = <KioskThankYouScreen onHome={() => flow.transitionTo("RETURN_IDLE")}/>;
  else if (RECOGNITION.has(state)) content = <div className={`recognition-stage ${state === "UNKNOWN_FACE" ? "unknown" : ""}`}>
    <div className="recognition-camera"><CameraPreview videoRef={camera.videoRef} status={camera.cameraStatus} error={camera.error} showFrameOverlay={false}/></div>
    <div className="recognition-copy">
      <AssistantAvatar mood={state === "UNKNOWN_FACE" ? "unknown" : state === "FACE_RECOGNIZING" ? "thinking" : "greeting"}/>
      {state === "UNKNOWN_FACE" ? <>
        <div className="unknown-face-icon" aria-hidden="true">😔</div>
        <h1>Chưa nhận ra khuôn mặt.</h1>
        <p>Bạn chưa đăng ký dữ liệu khuôn mặt.</p>
        <small>Vui lòng đăng ký khuôn mặt. Hệ thống vẫn đang tiếp tục nhận diện.</small>
        <button onClick={() => { kioskEvents.publish(Events.registrationRequested); kioskStream.send(Events.registrationRequested); }}>Đăng ký khuôn mặt</button>
      </> : <>
        <span className="kiosk-kicker">NHẬN DIỆN THỜI GIAN THỰC</span>
        <h1>{state === "FACE_RECOGNIZING" ? "Đang xác nhận danh tính…" : "Vui lòng nhìn vào camera"}</h1>
        <p aria-live="polite">{sensor.guidance}</p>
        <div className={`quality-indicator ${sensor.qualityReady ? "ready" : ""}`}><i/>{sensor.qualityReady ? "Khuôn mặt đã sẵn sàng" : "Đang kiểm tra chất lượng"}</div>
      </>}
    </div>
  </div>;
  else content = <div className="kiosk-center assistant-stage">
    <AssistantAvatar mood={state === "ERROR" ? "error" : state === "UNKNOWN_FACE" ? "unknown" : state === "FACE_RECOGNIZED" || state === "REGISTER_SUCCESS" ? "happy" : state === "RETURN_IDLE" ? "goodbye" : state === "IDLE" ? "idle" : "greeting"}/>
    <span className="kiosk-kicker">TRỢ LÝ AI THƯ VIỆN</span>
    <h1>{state === "IDLE" ? "Xin chào, tôi có thể giúp bạn" : state === "FACE_RECOGNIZED" || state === "REGISTER_SUCCESS" ? "Rất vui được gặp bạn!" : state === "RETURN_IDLE" ? "Hẹn gặp lại" : state === "ERROR" ? "Trợ lý tạm thời gián đoạn" : "Chào mừng bạn đến thư viện"}</h1>
    <p aria-live="polite">{flow.error ?? (state === "IDLE" ? "Hãy đến gần để trò chuyện cùng tôi" : sensor.guidance)}</p>
    {state === "ERROR" && <button onClick={() => void flow.resetToIdle("ERROR_RECOVERY")}>Về màn hình chờ</button>}
  </div>;
  return <KioskChrome state={state} onExit={state !== "IDLE" ? () => flow.transitionTo("SURVEY") : undefined}>
    {content}
    {import.meta.env.DEV && import.meta.env.VITE_ENABLE_DEV_CONTROLS === "true" && <details className="kiosk-dev-panel"><summary>Runtime diagnostics</summary><pre>{JSON.stringify({ state, camera: camera.cameraStatus, presence: sensor.externalPresence ? "external sensor" : "not connected", ...sensor.diagnostics }, null, 2)}</pre><button onClick={() => void flow.startSession()}>Simulate presence</button></details>}
  </KioskChrome>;
}
