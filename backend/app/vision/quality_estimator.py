from dataclasses import dataclass
from typing import Any

from app.vision.face_detector import DetectedFace
from app.vision.face_tracker import Track


@dataclass(frozen=True)
class QualityResult:
    accepted: bool
    guidance: str | None
    score: float
    metrics: dict[str, float | int | bool]


class QualityEstimator:
    def estimate(self, image: Any, face: DetectedFace, track: Track, face_count: int, now: float) -> QualityResult:
        import numpy as np
        top, right, bottom, left = face.box
        crop = image[top:bottom, left:right].mean(axis=2)
        face_size = min(bottom - top, right - left)
        brightness = float(crop.mean())
        laplacian = -4 * crop[1:-1, 1:-1] + crop[:-2, 1:-1] + crop[2:, 1:-1] + crop[1:-1, :-2] + crop[1:-1, 2:]
        blur_score = float(np.var(laplacian))
        marks = face.landmarks
        eyes = [np.asarray(marks[name]) for name in ("left_eye", "right_eye")]
        eye_ratios = [float(np.linalg.norm(eye[1] - eye[5]) / max(1, np.linalg.norm(eye[0] - eye[3]))) for eye in eyes]
        eyes_open = all(ratio > .14 for ratio in eye_ratios)
        centers = [eye.mean(axis=0) for eye in eyes]
        eye_span = max(1, np.linalg.norm(centers[0] - centers[1]))
        nose = np.asarray(marks["nose_tip"]).mean(axis=0)
        midpoint = (centers[0] + centers[1]) / 2
        yaw_ratio = float(abs(nose[0] - midpoint[0]) / eye_span)
        roll_ratio = float(abs(centers[0][1] - centers[1][1]) / eye_span)
        frontal = yaw_ratio < .28 and roll_ratio < .16
        metrics = {"face_size_px": face_size, "brightness": round(brightness, 1),
                   "blur_score": round(blur_score, 1), "eyes_open": eyes_open,
                   "eye_ratio": round(min(eye_ratios), 3), "yaw_ratio": round(yaw_ratio, 3),
                   "roll_ratio": round(roll_ratio, 3)}
        if face_count != 1:
            return QualityResult(False, "Vui lòng đứng một mình trước kiosk", 0, metrics)
        if face_size < 160:
            return QualityResult(False, "Vui lòng đến gần hơn", .2, metrics)
        if brightness < 55:
            return QualityResult(False, "Khuôn mặt đang thiếu sáng", .3, metrics)
        if brightness > 205:
            return QualityResult(False, "Ánh sáng phía sau quá mạnh", .3, metrics)
        if blur_score < 75:
            return QualityResult(False, "Giữ yên khuôn mặt", .4, metrics)
        if not eyes_open or not frontal:
            return QualityResult(False, "Vui lòng nhìn thẳng vào camera", .5, metrics)
        if track.hits < 3 or now - track.stable_since < .35:
            return QualityResult(False, "Giữ yên trong giây lát", .7, metrics)
        return QualityResult(True, None, 1.0, metrics)
