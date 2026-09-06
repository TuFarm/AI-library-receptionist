import { useCallback, useEffect, useRef, useState } from "react";
import { CameraManager } from "../runtime/CameraManager";
import type { CameraStatus } from "../types/kiosk";

export function useCamera() {
  const managerRef = useRef(new CameraManager());
  const requestRef = useRef<Promise<boolean> | null>(null);
  const [videoElement, setVideoElement] = useState<HTMLVideoElement | null>(null);
  const [cameraStatus, setCameraStatus] = useState<CameraStatus>("IDLE");
  const [error, setError] = useState<string | null>(null);

  const stopCamera = useCallback(() => {
    managerRef.current.stop();
    setCameraStatus("STOPPED");
  }, []);

  const requestCamera = useCallback(async () => {
    if (requestRef.current) return requestRef.current;
    const request = (async () => {
      if (!navigator.mediaDevices?.getUserMedia) {
        setError("Thiết bị này không hỗ trợ truy cập camera.");
        setCameraStatus("ERROR");
        return false;
      }
      setCameraStatus("REQUESTING"); setError(null);
      try {
        const started = await managerRef.current.start();
        if (started) setCameraStatus("READY");
        return started;
      } catch (reason) {
        const denied = reason instanceof DOMException && (reason.name === "NotAllowedError" || reason.name === "SecurityError");
        setCameraStatus(denied ? "DENIED" : "ERROR");
        setError(denied
          ? "Camera chưa được cấp quyền. Vui lòng cho phép camera để tiếp tục."
          : "Không thể mở camera. Vui lòng kiểm tra thiết bị và thử lại.");
        return false;
      }
    })();
    requestRef.current = request;
    try { return await request; }
    finally { requestRef.current = null; }
  }, []);

  const captureFrame = useCallback(async () => {
    return managerRef.current.captureNativeFrame();
  }, []);

  const videoRef = useCallback((video: HTMLVideoElement | null) => {
    managerRef.current.setPreview(video);
    setVideoElement(video);
  }, []);

  useEffect(() => stopCamera, [stopCamera]);
  return { videoRef, videoElement, requestCamera, stopCamera, captureFrame, cameraStatus, error };
}
