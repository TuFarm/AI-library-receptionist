import { kioskStream } from "../../runtime/stream";
import { AssistantAvatar } from "../../components/kiosk/AssistantAvatar";
import { KioskChrome } from "../../components/kiosk/KioskChrome";
import { useCamera } from "../../hooks/useCamera";
import { useKioskFlow } from "../../hooks/useKioskFlow";
import { useRealtimeSensor } from "../../runtime/useRealtimeSensor";
import FaceRegistrationScreen from "./FaceRegistrationScreen";
import EnrollmentSuccessScreen from "./EnrollmentSuccessScreen";
import KioskSurveyScreen from "./KioskSurveyScreen";
import KioskThankYouScreen from "./KioskThankYouScreen";
import KioskVoiceChatScreen from "./KioskVoiceChatScreen";
import WelcomeScreen from "./WelcomeScreen";
import { isRecognitionState, RecognitionScreen } from "./RecognitionScreen";
import { kioskEvents } from "../../runtime/eventBus";
import { RuntimeEvent as Events } from "../../runtime/events";

const VOICE = new Set(["AI_GREETING", "VOICE_LISTENING", "USER_SPEAKING", "PROCESSING", "AI_SPEAKING", "LISTENING"]);
export default function KioskApp() {
  const flow = useKioskFlow();
  const camera = useCamera();
  const sensor = useRealtimeSensor(flow, camera);
  const state = flow.currentState;
  let content;
  if (VOICE.has(state)) content = <KioskVoiceChatScreen flow={flow}/>;
  else if (state === "REGISTER" || state === "REGISTER_PROCESSING") content = <FaceRegistrationScreen videoRef={camera.videoRef} cameraStatus={camera.cameraStatus}
    cameraError={camera.error} busy={flow.isProcessing} captureFrame={sensor.captureEnrollmentFrame} qualityReady={sensor.qualityReady}
    faceCount={sensor.faceCount} multipleFacesDetected={sensor.multipleFacesDetected} onEnroll={flow.enrollFace}
    capturePrepared={sensor.capturePrepared} captureCountdown={sensor.captureCountdown}
    onCaptureStart={sensor.beginEnrollmentCapture} onCaptureEnd={sensor.endEnrollmentCapture}
    onCancel={() => flow.transitionTo("UNKNOWN_FACE")}/>;
  else if (state === "REGISTER_SUCCESS") content = <EnrollmentSuccessScreen user={flow.user} welcomeContext={flow.welcomeContext}
    onComplete={() => flow.transitionTo("WELCOME")}/>;
  else if (state === "WELCOME") content = <WelcomeScreen user={flow.user} welcomeContext={flow.welcomeContext}
    announce={flow.welcomeContext === "returning"} frozenFrameUrl={sensor.frozenFrameUrl}
    onContinue={() => void flow.startConversation()} onSave={flow.updateProfile}
    onReregister={() => flow.transitionTo("REGISTER")}
    onDeleteFaceId={async () => { await flow.deleteFaceId(); await flow.resetToIdle("FACE_ID_DELETED"); }}/>;
  else if (state === "SURVEY") content = <KioskSurveyScreen sessionId={flow.session?.session_id} userId={flow.user?.id} onComplete={flow.completeSurvey}/>;
  else if (state === "THANK_YOU") content = <KioskThankYouScreen onHome={() => flow.transitionTo("RETURN_IDLE")}/>;
  else if (isRecognitionState(state)) content = <RecognitionScreen state={state} videoRef={camera.videoRef}
    cameraStatus={camera.cameraStatus} cameraError={camera.error} guidance={sensor.guidance} qualityReady={sensor.qualityReady}
    faceCount={sensor.faceCount} multipleFacesDetected={sensor.multipleFacesDetected}
    onRegister={() => { kioskEvents.publish(Events.registrationRequested); kioskStream.send(Events.registrationRequested); }}/>;
  else content = <div className="kiosk-center assistant-stage">
    <AssistantAvatar mood={state === "ERROR" ? "error" : state === "UNKNOWN_FACE" ? "unknown" : state === "FACE_RECOGNIZED" ? "happy" : state === "RETURN_IDLE" ? "goodbye" : state === "IDLE" ? "idle" : "greeting"}/>
    <span className="kiosk-kicker">TRỢ LÝ AI THƯ VIỆN</span>
    <h1>{state === "IDLE" ? "Xin chào, tôi có thể giúp bạn" : state === "FACE_RECOGNIZED" ? "Rất vui được gặp bạn!" : state === "RETURN_IDLE" ? "Hẹn gặp lại" : state === "ERROR" ? "Trợ lý tạm thời gián đoạn" : "Chào mừng bạn đến thư viện"}</h1>
    <p aria-live="polite">{flow.error ?? (state === "IDLE" ? "Hãy đến gần để trò chuyện cùng tôi" : sensor.guidance)}</p>
    {state === "ERROR" && <button onClick={() => void flow.resetToIdle("ERROR_RECOVERY")}>Về màn hình chờ</button>}
  </div>;
  return <KioskChrome state={state} onExit={state !== "IDLE" ? () => flow.transitionTo("SURVEY") : undefined}>
    {content}
  </KioskChrome>;
}
