from time import monotonic

from app.vision.face_detector import FaceDetector
from app.vision.face_tracker import FaceTracker
from app.vision.image_decoder import ImageDecoder
from app.vision.quality_estimator import QualityEstimator


class VisionEngine:
    def __init__(self, decoder=None, detector=None, tracker=None, quality=None):
        self.decoder = decoder or ImageDecoder()
        self.detector = detector or FaceDetector()
        self.tracker = tracker or FaceTracker()
        self.quality = quality or QualityEstimator()
        self.metrics = {}
        self._last_completed = None
        self._provider_detections = {}

    @property
    def tracks(self):
        return self.tracker.tracks

    def provider_detection(self, track_id: int):
        return self._provider_detections.get(track_id)

    def inspect(self, data):
        started = monotonic()
        image = self.decoder.decode(data)
        decoded = monotonic()
        faces = self.detector.detect(image)
        detected = monotonic()
        now = detected
        tracks = self.tracker.update([face.box for face in faces], now)
        self._provider_detections = {}
        results = []
        for face, track in zip(faces, tracks, strict=True):
            self._provider_detections[track.id] = face.provider_detection
            quality = self.quality.estimate(image, face, track, len(tracks), now)
            if not quality.accepted:
                track.reset()
            landmarks = [[int(x), int(y)] for points in face.landmarks.values() for x, y in points]
            results.append({
                "track_id": track.id,
                "box": list(track.box),
                "landmarks": landmarks,
                "quality_ok": quality.accepted,
                "quality_score": quality.score,
                "guidance": quality.guidance,
                "quality_metrics": quality.metrics,
                "box_iou": round(track.last_iou, 4),
                "track_hits": track.hits,
                "track_age_ms": round((now - track.stable_since) * 1000),
            })
        completed = monotonic()
        interval = completed - self._last_completed if self._last_completed is not None else None
        self._last_completed = completed
        self.metrics = {
            "decode_ms": round((decoded - started) * 1000, 1),
            "detection_ms": round((detected - decoded) * 1000, 1),
            "quality_tracking_ms": round((completed - detected) * 1000, 1),
            "vision_ms": round((completed - started) * 1000, 1),
            "detection_fps": round(1 / interval, 1) if interval and interval > 0 else None,
            **self.tracker.metrics,
        }
        return image, results
