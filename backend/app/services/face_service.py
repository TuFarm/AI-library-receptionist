import json
import math
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Iterable
from uuid import UUID

from app.core.config import settings
from app.utils.image_utils import filename_requests_unknown


class FaceProviderUnavailable(RuntimeError):
    pass


class FaceImageError(ValueError):
    pass


@dataclass
class FaceEnrollmentResult:
    template_ref: str | None
    template_bytes: bytes | None
    model_name: str
    quality_score: float


@dataclass
class FaceVerificationResult:
    result: str
    user_id: UUID | None
    confidence_score: float | None
    distance: float | None = None
    embedding_dimension: int | None = None
    embedding_norm: float | None = None


FaceCandidate = tuple[UUID, bytes | None, str | None]


def _load_local_library():
    try:
        import face_recognition  # type: ignore[import-not-found]
    except (ImportError, SystemExit) as exc:
        raise FaceProviderUnavailable(
            "FaceID cục bộ chưa sẵn sàng. Hãy cài lại requirements-face-local.txt "
            "(bao gồm setuptools<82 cho face_recognition_models) hoặc chuyển "
            "FACE_PROVIDER=mock."
        ) from exc
    return face_recognition


def _extract_single_encoding(image_path: Path):
    face_recognition = _load_local_library()
    image = face_recognition.load_image_file(str(image_path))
    locations = face_recognition.face_locations(image, model="hog")
    if not locations:
        raise FaceImageError("Không phát hiện khuôn mặt trong ảnh. Vui lòng nhìn thẳng vào camera.")
    if len(locations) != 1:
        raise FaceImageError("Ảnh đăng ký phải có đúng một khuôn mặt.")
    encodings = face_recognition.face_encodings(image, known_face_locations=locations)
    if len(encodings) != 1:
        raise FaceImageError("Không thể trích xuất đặc trưng khuôn mặt từ ảnh.")
    return encodings[0]


class FaceService:
    def enroll_face(self, user_id: UUID, image_path: Path) -> FaceEnrollmentResult:
        if settings.face_provider == "local":
            encoding = _extract_single_encoding(image_path)
            serialized = json.dumps([float(value) for value in encoding]).encode("utf-8")
            return FaceEnrollmentResult(None, serialized, "face-recognition-hog-128d", 1.0)
        digest = sha256(image_path.read_bytes()).hexdigest()
        return FaceEnrollmentResult(f"mock://face/{user_id}/{digest}", None, "mock-face-v1", 0.95)

    def verify_face(self, image_path: Path, candidates: Iterable[FaceCandidate] | UUID | None) -> FaceVerificationResult:
        # UUID/None compatibility keeps the Phase 3 service boundary usable.
        if isinstance(candidates, UUID):
            candidate_list: list[FaceCandidate] = [(candidates, None, None)]
        elif candidates is None:
            candidate_list = []
        else:
            candidate_list = list(candidates)
        if settings.face_provider == "local":
            probe = _extract_single_encoding(image_path)
            return self.verify_encoding(probe, candidate_list)

        candidate_user_id = candidate_list[0][0] if candidate_list else None
        if "low" in image_path.name.lower():
            return FaceVerificationResult("LOW_CONFIDENCE", None, min(0.60, settings.face_confidence_threshold - 0.01))
        if filename_requests_unknown(image_path) or candidate_user_id is None:
            return FaceVerificationResult("UNKNOWN_FACE", None, 0.31)
        confidence = 0.94
        if confidence < settings.face_confidence_threshold:
            return FaceVerificationResult("LOW_CONFIDENCE", None, confidence)
        return FaceVerificationResult("SUCCESS", candidate_user_id, confidence)

    def verify_encoding(self, probe, candidates: Iterable[FaceCandidate]) -> FaceVerificationResult:
        """Match one dlib 128D descriptor. The score is display calibration, not probability."""
        return self.verify_prepared_encoding(probe, self.prepare_candidates(candidates))

    @staticmethod
    def prepare_candidates(candidates: Iterable[FaceCandidate]):
        prepared = []
        for user_id, template_bytes, _template_ref in candidates:
            if not template_bytes:
                continue
            try:
                values = [float(value) for value in json.loads(template_bytes.decode("utf-8"))]
                if len(values) == 128 and all(math.isfinite(value) for value in values):
                    prepared.append((user_id, values))
            except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
                continue
        return prepared

    def verify_prepared_encoding(self, probe, prepared) -> FaceVerificationResult:
        face_recognition = _load_local_library()
        probe_values = [float(value) for value in probe]
        dimension = len(probe_values)
        norm = math.sqrt(sum(value * value for value in probe_values))
        if dimension != 128 or not math.isfinite(norm):
            raise FaceImageError("Đặc trưng khuôn mặt không hợp lệ.")
        if not prepared:
            return FaceVerificationResult("UNKNOWN_FACE", None, None, embedding_dimension=dimension, embedding_norm=round(norm, 4))
        valid_users = [user_id for user_id, _encoding in prepared]
        known_encodings = [encoding for _user_id, encoding in prepared]
        # face_recognition.face_distance subtracts its arguments directly; both
        # operands must be NumPy arrays rather than the JSON-derived Python lists.
        known_array = face_recognition.api.np.asarray(known_encodings, dtype=float)
        probe_array = face_recognition.api.np.asarray(probe_values, dtype=float)
        distances = face_recognition.face_distance(known_array, probe_array)
        best_index = min(range(len(distances)), key=lambda index: float(distances[index]))
        distance = float(distances[best_index])
        # Maps the operational distance threshold 0.60 to a readable score of 75%.
        confidence = round(max(0.0, min(1.0, 1.0 - distance / 2.4)), 4)
        common = {"confidence_score": confidence, "distance": round(distance, 4),
                  "embedding_dimension": dimension, "embedding_norm": round(norm, 4)}
        if distance <= settings.face_distance_threshold:
            return FaceVerificationResult("SUCCESS", valid_users[best_index], **common)
        result = "LOW_CONFIDENCE" if distance <= settings.face_distance_threshold + .15 else "UNKNOWN_FACE"
        return FaceVerificationResult(result, None, **common)
