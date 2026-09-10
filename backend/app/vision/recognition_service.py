from time import monotonic
import json
import math

from app.core.config import settings
from app.services.face_service import (
    FaceImageError,
    FaceProviderUnavailable,
    FaceService,
    FaceVerificationResult,
    MultipleFacesDetectedError,
    NoFaceDetectedError,
    ProviderFaceDetection,
    QualityGatedFace,
    VersionedFaceEmbedding,
    get_face_provider,
)


class RecognitionService:
    def __init__(self):
        self.metrics = {}
        self.gallery = None
        self.profile_query_ms = 0.0
        self.gallery_loaded_at: float | None = None
        self.cadence_seconds = settings.face_recognition_cadence_ms / 1000

    def should_recognize(self, track, now: float) -> bool:
        return now - track.last_recognition >= self.cadence_seconds

    def gallery_expired(self, now: float) -> bool:
        return (
            self.gallery_loaded_at is None
            or settings.face_gallery_ttl_ms == 0
            or (now - self.gallery_loaded_at) * 1000 >= settings.face_gallery_ttl_ms
        )

    def refresh_gallery(self, now: float) -> None:
        self.gallery = None
        self.gallery_loaded_at = now

    @staticmethod
    def _opencv_gallery(candidates, provider):
        gallery = []
        for candidate in candidates:
            if len(candidate) != 5:
                continue
            user_id, template_bytes, _template_ref, model_name, model_version = candidate
            if not template_bytes or not provider.supports_profile(model_name, model_version):
                continue
            try:
                values = [float(value) for value in json.loads(template_bytes.decode("utf-8"))]
                norm = math.sqrt(sum(value * value for value in values))
            except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if (
                len(values) != provider.embedding_dimension
                or not all(math.isfinite(value) for value in values)
                or not math.isfinite(norm)
                or abs(norm - 1.0) > 1e-4
            ):
                continue
            gallery.append((
                user_id,
                VersionedFaceEmbedding(model_name, model_version, len(values), values),
            ))
        return gallery

    def recognize(self, image, detections, candidates, quality_accepted=True):
        started = monotonic()
        provider = get_face_provider()
        if not detections:
            raise NoFaceDetectedError("Không phát hiện khuôn mặt trong ảnh.")
        if len(detections) > 1:
            raise MultipleFacesDetectedError(len(detections))
        if not quality_accepted:
            raise FaceImageError("Khuôn mặt chưa đạt yêu cầu chất lượng.")
        detection = detections[0]
        if not isinstance(detection, ProviderFaceDetection):
            detection = ProviderFaceDetection(tuple(detection))
        if provider.name == "opencv-sface-128d":
            probe = provider.create_embedding(
                image,
                QualityGatedFace.from_detections([detection], quality_accepted=True),
            )
        else:
            probe = provider.create_embedding(image, detection)
        encoded = monotonic()
        gallery_started = monotonic()
        if self.gallery is None:
            self.gallery = (
                self._opencv_gallery(candidates, provider)
                if provider.name == "opencv-sface-128d"
                else FaceService.prepare_candidates(candidate[:3] for candidate in candidates)
            )
        gallery_loaded = monotonic()
        if provider.name == "opencv-sface-128d":
            if not isinstance(probe, VersionedFaceEmbedding):
                raise FaceImageError("Đặc trưng khuôn mặt thiếu thông tin phiên bản.")
            if not self.gallery:
                result = FaceVerificationResult(
                    "UNKNOWN_FACE", None, None, embedding_dimension=probe.dimension,
                    embedding_norm=1.0,
                )
            else:
                users = [user_id for user_id, _embedding in self.gallery]
                similarities = provider.compare_embeddings(
                    [embedding for _user_id, embedding in self.gallery], probe
                )
                best_index = max(
                    range(len(similarities)), key=lambda index: float(similarities[index])
                )
                similarity = float(similarities[best_index])
                matched = provider.is_match(similarity)
                result = FaceVerificationResult(
                    "SUCCESS" if matched else "UNKNOWN_FACE",
                    users[best_index] if matched else None,
                    max(0.0, min(1.0, similarity)),
                    distance=1.0 - similarity,
                    embedding_dimension=probe.dimension,
                    embedding_norm=1.0,
                )
        else:
            result = FaceService().verify_prepared_encoding(probe, self.gallery, provider=provider)
        completed = monotonic()
        distance_threshold = settings.face_distance_threshold
        if provider.name == "opencv-sface-128d":
            distance_threshold = (
                None if provider.cosine_threshold is None else 1.0 - provider.cosine_threshold
            )
        self.metrics = {
            "embedding_ms": round((encoded - started) * 1000, 1),
            "search_ms": round((completed - gallery_loaded) * 1000, 1),
            "gallery_load_ms": round((gallery_loaded - gallery_started) * 1000, 1),
            "profile_query_ms": round(self.profile_query_ms, 1),
            "gallery_size": len(self.gallery),
            "recognition_ms": round((completed - started) * 1000, 1),
            "embedding_dimension": result.embedding_dimension,
            "embedding_norm": result.embedding_norm,
            "distance": result.distance,
            "distance_threshold": distance_threshold,
            "face_provider": provider.name,
        }
        self.profile_query_ms = 0.0
        return result


__all__ = ["RecognitionService", "FaceProviderUnavailable"]
