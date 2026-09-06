from dataclasses import dataclass
from typing import Any

from app.services.face_service import _load_local_library


@dataclass(frozen=True)
class DetectedFace:
    box: tuple[int, int, int, int]
    landmarks: dict[str, list[tuple[int, int]]]


class FaceDetector:
    """Runs detection for every accepted frame; recognition has its own slower cadence."""

    def __init__(self, analysis_width: int = 640):
        self.analysis_width = analysis_width

    def detect(self, image: Any) -> list[DetectedFace]:
        library = _load_local_library()
        height, width = image.shape[:2]
        scale = min(1.0, self.analysis_width / width)
        analysis = image
        if scale < 1.0:
            import numpy as np
            from PIL import Image
            analysis = np.asarray(Image.fromarray(image).resize(
                (round(width * scale), round(height * scale)), Image.Resampling.BILINEAR
            ))
        boxes = library.face_locations(analysis, model="hog")
        landmarks = library.face_landmarks(analysis, boxes)
        inverse = 1.0 / scale

        def point(value):
            return tuple((round(x * inverse), round(y * inverse)) for x, y in value)

        return [DetectedFace(
            tuple(round(value * inverse) for value in box),
            {name: point(points) for name, points in marks.items()},
        ) for box, marks in zip(boxes, landmarks, strict=True)]
