import { useEffect, useRef, useState } from "react";
import { KIOSK_MOTION, KIOSK_TIMING } from "../config/kioskRuntime";
import { PixelMotionDetector } from "../runtime/pixelMotionDetector";

type DetectorMode = "idle" | "off";
export type VisualDetectionState = { mode: DetectorMode; present: boolean; warmedUp: boolean; guidance: string };
type NativeFaceDetector = { detect: (source: HTMLVideoElement) => Promise<Array<{ boundingBox: DOMRectReadOnly }>> };
type FaceDetectorConstructor = new (options?: { fastMode?: boolean; maxDetectedFaces?: number }) => NativeFaceDetector;
type VisualDetectionCallbacks = { onActivity?: () => void; onPresence?: () => void; onPresenceLost?: () => void };

const detectorConfig = {
  width: KIOSK_MOTION.canvasWidth, height: KIOSK_MOTION.canvasHeight, roi: KIOSK_MOTION.roi,
  warmupSamples: KIOSK_MOTION.warmupSamples, historySamples: KIOSK_MOTION.historySamples,
  requiredMotionSamples: KIOSK_MOTION.requiredMotionSamples, confirmationMs: KIOSK_TIMING.presenceConfirmationMs,
  absenceMs: KIOSK_TIMING.presenceAbsenceMs, cooldownMs: KIOSK_TIMING.presenceWakeCooldownMs,
  pixelDelta: KIOSK_MOTION.pixelDelta, enterRatio: KIOSK_MOTION.enterRatio,
  exitRatio: KIOSK_MOTION.exitRatio, baselineAlpha: KIOSK_MOTION.baselineAlpha,
};

export function useVisualDetection(video: HTMLVideoElement | null, mode: DetectorMode, callbacks: VisualDetectionCallbacks = {}): VisualDetectionState {
  const [state, setState] = useState<VisualDetectionState>({ mode: "off", present: false, warmedUp: false, guidance: "Đang khởi động cảm biến hình ảnh" });
  const callbacksRef = useRef(callbacks); callbacksRef.current = callbacks;
  useEffect(() => {
    const detector = new PixelMotionDetector(detectorConfig);
    const canvas = document.createElement("canvas");
    canvas.width = detectorConfig.width; canvas.height = detectorConfig.height;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    let nativeDetector: NativeFaceDetector | null = null;
    let nativeFace = false;
    let lastNativeSampleAt = -Infinity;
    let timer: number | undefined;
    let active = true;
    setState({ mode, present: false, warmedUp: false, guidance: mode === "off" ? "Cảm biến hình ảnh đang tắt" : "Đang hiệu chỉnh vùng quan sát" });
    if (mode === "off" || !video || !context) return;

    const sample = async () => {
      if (!active) return;
      if (video.readyState >= 2 && video.videoWidth) {
        const now = performance.now();
        const NativeDetector = (window as Window & { FaceDetector?: FaceDetectorConstructor }).FaceDetector;
        if (NativeDetector && !nativeDetector) nativeDetector = new NativeDetector({ fastMode: true, maxDetectedFaces: 1 });
        if (nativeDetector && now - lastNativeSampleAt >= KIOSK_MOTION.nativeFaceSampleMs) {
          lastNativeSampleAt = now;
          try {
            const faces = await nativeDetector.detect(video);
            const box = faces.length === 1 ? faces[0].boundingBox : null;
            const centerX = box ? (box.x + box.width / 2) / video.videoWidth : -1;
            const centerY = box ? (box.y + box.height / 2) / video.videoHeight : -1;
            const roi = KIOSK_MOTION.roi;
            nativeFace = Boolean(box && centerX >= roi.x && centerX <= roi.x + roi.width && centerY >= roi.y && centerY <= roi.y + roi.height);
          } catch { nativeDetector = null; nativeFace = false; }
        }
        context.drawImage(video, 0, 0, detectorConfig.width, detectorConfig.height);
        const rgba = context.getImageData(0, 0, detectorConfig.width, detectorConfig.height).data;
        const gray = new Uint8ClampedArray(detectorConfig.width * detectorConfig.height);
        for (let source = 0, target = 0; source < rgba.length; source += 4, target += 1) gray[target] = (rgba[source] * 3 + rgba[source + 1] * 6 + rgba[source + 2]) / 10;
        const observation = detector.observe(gray, now, nativeFace);
        if (observation.moving || nativeFace) callbacksRef.current.onActivity?.();
        if (observation.wake) callbacksRef.current.onPresence?.();
        if (observation.lost) callbacksRef.current.onPresenceLost?.();
        setState(previous => previous.present === observation.present && previous.warmedUp === observation.warmedUp && previous.mode === mode
          ? previous : { mode, present: observation.present, warmedUp: observation.warmedUp,
            guidance: observation.warmedUp ? (observation.present ? "Đã phát hiện người dùng" : "Đang quan sát khu vực phía trước kiosk") : "Đang hiệu chỉnh vùng quan sát" });
      }
      if (active) timer = window.setTimeout(() => { void sample(); }, KIOSK_TIMING.presenceSampleMs);
    };
    void sample();
    return () => { active = false; window.clearTimeout(timer); detector.reset(); canvas.width = 0; canvas.height = 0; };
  }, [mode, video]);
  return state;
}
