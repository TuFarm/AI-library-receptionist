import type { Ref } from "react";
import type { CameraStatus, FaceGuideRect } from "../../types/kiosk";

const labels: Record<CameraStatus, string> = {
  IDLE: "Camera chưa khởi động", REQUESTING: "Đang xin quyền camera…", READY: "Camera sẵn sàng",
  DENIED: "Camera chưa được cấp quyền", ERROR: "Camera gặp lỗi", STOPPED: "Camera đã dừng",
};
export function CameraPreview({ videoRef, status, error, showFrameOverlay = true, className = "", faceCount = 0,
  qualityReady = false, multipleFacesDetected = false, kioskState, faceGuideRects = [] }: {
  videoRef: Ref<HTMLVideoElement>; status: CameraStatus; error?: string | null; showFrameOverlay?: boolean; className?: string;
  faceCount?: number; qualityReady?: boolean; multipleFacesDetected?: boolean; kioskState?: string;
  faceGuideRects?: FaceGuideRect[];
}) {
  const guideState = multipleFacesDetected || faceCount > 1 ? "multiple"
    : kioskState === "UNKNOWN_FACE" ? "unknown"
    : faceCount === 1 && qualityReady ? "ready"
    : faceCount === 1 ? "analyzing" : "neutral";
  return <div className={`camera-preview ${className}`}>
    <video ref={videoRef} autoPlay muted playsInline aria-label="Hình ảnh trực tiếp từ camera kiosk" />
    {status !== "READY" && <div className="camera-fallback"><span>◎</span><strong>{labels[status]}</strong>{error && <p>{error}</p>}</div>}
    {showFrameOverlay && faceGuideRects.map((rect, index) => <div key={index}
      className={`face-frame face-guide-${multipleFacesDetected ? "multiple" : rect.quality_ok && qualityReady ? "ready" : guideState}`}
      aria-hidden="true" style={{ left: `${rect.x_pct}%`, top: `${rect.y_pct}%`, width: `${rect.width_pct}%`, height: `${rect.height_pct}%` }}/>) }
    <span className={`camera-status ${status.toLowerCase()}`}><i/>{labels[status]}</span>
  </div>;
}
