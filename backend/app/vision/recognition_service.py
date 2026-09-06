from time import monotonic

from app.core.config import settings
from app.services.face_service import FaceImageError, FaceProviderUnavailable, FaceService, _load_local_library


class RecognitionService:
    cadence_seconds = .5

    def __init__(self):
        self.metrics = {}
        self.gallery = None

    def should_recognize(self, track, now: float) -> bool:
        return now - track.last_recognition >= self.cadence_seconds

    def recognize(self, image, box, candidates):
        started = monotonic()
        library = _load_local_library()
        encodings = library.face_encodings(image, known_face_locations=[tuple(box)])
        encoded = monotonic()
        if len(encodings) != 1:
            raise FaceImageError("Không thể trích xuất đặc trưng khuôn mặt từ vùng đã theo dõi.")
        gallery_started = monotonic()
        if self.gallery is None:
            self.gallery = FaceService.prepare_candidates(candidates)
        gallery_loaded = monotonic()
        result = FaceService().verify_prepared_encoding(encodings[0], self.gallery)
        completed = monotonic()
        self.metrics = {
            "embedding_ms": round((encoded - started) * 1000, 1),
            "search_ms": round((completed - gallery_loaded) * 1000, 1),
            "gallery_load_ms": round((gallery_loaded - gallery_started) * 1000, 1),
            "gallery_size": len(self.gallery),
            "recognition_ms": round((completed - started) * 1000, 1),
            "embedding_dimension": result.embedding_dimension,
            "embedding_norm": result.embedding_norm,
            "distance": result.distance,
            "distance_threshold": settings.face_distance_threshold,
        }
        return result


__all__ = ["RecognitionService", "FaceProviderUnavailable"]
