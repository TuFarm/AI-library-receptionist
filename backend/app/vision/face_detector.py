from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.services.face_service import ProviderFaceDetection, get_face_provider


@dataclass(frozen=True)
class DetectedFace:
    box: tuple[int, int, int, int]
    landmarks: dict[str, list[tuple[int, int]]]
    provider_detection: ProviderFaceDetection


class FaceDetector:
    """Runs detection for every accepted frame; recognition has its own slower cadence."""

    def __init__(self, analysis_width: int | None = None):
        self.analysis_width = analysis_width or settings.face_analysis_width

    def detect(self, image: Any) -> list[DetectedFace]:
        provider = get_face_provider()
        height, width = image.shape[:2]
        scale = min(1.0, self.analysis_width / width)
        analysis = image
        if scale < 1.0:
            import numpy as np
            from PIL import Image
            analysis = np.asarray(Image.fromarray(image).resize(
                (round(width * scale), round(height * scale)), Image.Resampling.BILINEAR
            ))
        provider_detections = provider.detect_faces(analysis)
        provider_detections = provider.add_quality_input(analysis, provider_detections)
        inverse = 1.0 / scale
        scaled = [provider.scale_detection(detection, inverse) for detection in provider_detections]
        return [DetectedFace(detection.box, detection.quality_input, detection) for detection in scaled]
