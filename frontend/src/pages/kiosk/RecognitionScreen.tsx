import type { Ref } from "react";
import { AssistantAvatar } from "../../components/kiosk/AssistantAvatar";
import { CameraPreview } from "../../components/kiosk/CameraPreview";
import type { CameraStatus, FaceGuideRect, KioskState } from "../../types/kiosk";

const recognitionStates = new Set<KioskState>([
  "CAMERA_PREPARING", "FACE_TRACKING", "FACE_RECOGNIZING", "IDENTITY_CONFIRMING", "UNKNOWN_FACE",
]);

export function isRecognitionState(state: KioskState) { return recognitionStates.has(state); }

export function RecognitionScreen({ state, videoRef, cameraStatus, cameraError, guidance, qualityReady,
  faceCount, faceGuideRects, multipleFacesDetected, onRegister }: {
  state: KioskState; videoRef: Ref<HTMLVideoElement>; cameraStatus: CameraStatus; cameraError?: string | null;
  guidance: string; qualityReady: boolean; faceCount: number; faceGuideRects: FaceGuideRect[];
  multipleFacesDetected: boolean; onRegister: () => void;
}) {
  const unknown = state === "UNKNOWN_FACE";
  const confirming = state === "IDENTITY_CONFIRMING";
  const heading = unknown ? "Chưa nhận ra khuôn mặt" : confirming ? "Đang xác nhận danh tính…" : "Vui lòng nhìn vào camera";
  return <div className={`recognition-stage ${unknown ? "unknown" : ""}`}>
    <div className="recognition-camera"><CameraPreview videoRef={videoRef} status={cameraStatus} error={cameraError}
      showFrameOverlay faceCount={faceCount} faceGuideRects={faceGuideRects} qualityReady={qualityReady}
      multipleFacesDetected={multipleFacesDetected} kioskState={state}/></div>
    <div className="recognition-copy">
      <AssistantAvatar mood={unknown ? "unknown" : confirming ? "thinking" : "greeting"}/>
      {unknown && <div className="unknown-face-icon" aria-hidden="true">😔</div>}
      {!unknown && <span className="kiosk-kicker">NHẬN DIỆN THỜI GIAN THỰC</span>}
      <h1>{heading}</h1>
      {unknown ? <>
        <p>Bạn có thể đăng ký Face ID để sử dụng trợ lý.</p>
        <small>Hệ thống chỉ kết luận sau nhiều lần matching an toàn trên cùng khuôn mặt.</small>
        <button onClick={onRegister}>Đăng ký khuôn mặt</button>
      </> : <>
        <p aria-live="polite">{confirming ? "Đang hoàn tất xác nhận an toàn…" : guidance}</p>
        <div className={`quality-indicator ${qualityReady ? "ready" : ""}`}><i/>{qualityReady ? "Khuôn mặt đã sẵn sàng" : "Đang kiểm tra chất lượng"}</div>
      </>}
    </div>
  </div>;
}
