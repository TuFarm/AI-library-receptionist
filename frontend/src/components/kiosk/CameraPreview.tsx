import type { Ref } from "react";
import type { CameraStatus } from "../../types/kiosk";
import { TrackingDiagnostics } from "./TrackingDiagnostics";

const labels: Record<CameraStatus, string> = {
  IDLE: "Camera chưa khởi động", REQUESTING: "Đang xin quyền camera…", READY: "Camera sẵn sàng",
  DENIED: "Camera chưa được cấp quyền", ERROR: "Camera gặp lỗi", STOPPED: "Camera đã dừng",
};
export function CameraPreview({ videoRef, status, error, showFrameOverlay = true, className = "" }: {
  videoRef: Ref<HTMLVideoElement>; status: CameraStatus; error?: string | null; showFrameOverlay?: boolean; className?: string;
}) {
  return <div className={`camera-preview ${className}`}>
    <video ref={videoRef} autoPlay muted playsInline aria-label="Hình ảnh trực tiếp từ camera kiosk" />
    <TrackingDiagnostics developer={import.meta.env.DEV && import.meta.env.VITE_ENABLE_DEV_CONTROLS === "true"}/>
    {status !== "READY" && <div className="camera-fallback"><span>◎</span><strong>{labels[status]}</strong>{error && <p>{error}</p>}</div>}
    {showFrameOverlay && <div className="face-frame" aria-hidden="true"><i/><i/><i/><i/><span className="scan-line"/></div>}
    <span className={`camera-status ${status.toLowerCase()}`}><i/>{labels[status]}</span>
  </div>;
}
