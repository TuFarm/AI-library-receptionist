"""Compatibility exports for the original realtime service boundary."""
from app.vision.engine import VisionEngine
from app.vision.face_tracker import Track, overlap


class RealtimeFaceService(VisionEngine):
    def track(self, boxes, now):
        return self.tracker.update(boxes, now)
