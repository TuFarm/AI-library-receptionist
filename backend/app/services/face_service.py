import json
import math
from dataclasses import dataclass, field
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Any, Iterable, Protocol, Sequence
from uuid import UUID

from app.core.config import settings
from app.utils.image_utils import filename_requests_unknown


class FaceProviderUnavailable(RuntimeError):
    pass


class FaceImageError(ValueError):
    pass


class InvalidFaceImageError(FaceImageError):
    pass


class NoFaceDetectedError(FaceImageError):
    pass


class MultipleFacesDetectedError(FaceImageError):
    def __init__(self, face_count: int):
        super().__init__("Phát hiện nhiều khuôn mặt. Vui lòng chỉ để một người xuất hiện trong khung hình.")
        self.face_count = face_count


@dataclass
class FaceEnrollmentResult:
    template_ref: str | None
    template_bytes: bytes | None
    model_name: str
    model_version: str
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
VersionedFaceCandidate = tuple[UUID, bytes | None, str | None, str | None, str | None]


FaceBox = tuple[int, int, int, int]
QualityInput = dict[str, list[tuple[int, int]]]


@dataclass(frozen=True, repr=False)
class ProviderFaceDetection:
    """Provider-neutral face observation using (top, right, bottom, left)."""

    box: FaceBox
    quality_input: QualityInput = field(default_factory=dict)
    provider_input: Any = field(default=None, repr=False, compare=False)

    def __repr__(self) -> str:
        return "ProviderFaceDetection(<redacted>)"


@dataclass(frozen=True, repr=False)
class QualityGatedFace:
    """Exactly one provider detection accepted by the caller's quality gate."""

    detection: ProviderFaceDetection = field(repr=False, compare=False)

    @classmethod
    def from_detections(
        cls,
        detections: Sequence[ProviderFaceDetection],
        *,
        quality_accepted: bool,
    ) -> "QualityGatedFace":
        if not detections:
            raise NoFaceDetectedError(
                "Không phát hiện khuôn mặt trong ảnh. Vui lòng nhìn thẳng vào camera."
            )
        if len(detections) > 1:
            raise MultipleFacesDetectedError(len(detections))
        if not quality_accepted:
            raise FaceImageError("Khuôn mặt chưa đạt yêu cầu chất lượng.")
        return cls(detections[0])

    def __repr__(self) -> str:
        return "QualityGatedFace(<redacted>)"


@dataclass(frozen=True, repr=False)
class VersionedFaceEmbedding:
    """Backend-only embedding tagged to prevent cross-model comparison."""

    model_name: str
    model_version: str
    dimension: int
    values: Any = field(repr=False, compare=False)

    def __repr__(self) -> str:
        return (
            "VersionedFaceEmbedding("
            f"model_name={self.model_name!r}, model_version={self.model_version!r}, "
            f"dimension={self.dimension}, values=<redacted>)"
        )


class FaceProvider(Protocol):
    """Internal biometric boundary; its values must never be logged or emitted."""

    name: str
    model_version: str
    embedding_dimension: int

    def decode_image(self, image_path: Path) -> Any: ...

    def detect_faces(self, image: Any) -> list[ProviderFaceDetection]: ...

    def add_quality_input(
        self, image: Any, detections: Sequence[ProviderFaceDetection]
    ) -> list[ProviderFaceDetection]: ...

    def scale_detection(
        self, detection: ProviderFaceDetection, factor: float
    ) -> ProviderFaceDetection: ...

    def assess_enrollment_quality(self, image: Any, detection: ProviderFaceDetection) -> float: ...

    def create_embedding(self, image: Any, face: Any): ...

    def compare_embeddings(self, known_embeddings, probe_embedding): ...

    def supports_profile(self, model_name: str | None, model_version: str | None) -> bool: ...


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


class DlibFaceProvider:
    """Current face_recognition/dlib implementation behind the stable boundary."""

    name = "face-recognition-hog-128d"
    model_version = "1"
    embedding_dimension = 128

    def decode_image(self, image_path: Path):
        try:
            return _load_local_library().load_image_file(str(image_path))
        except (OSError, ValueError) as exc:
            raise InvalidFaceImageError("Ảnh khuôn mặt không hợp lệ.") from exc

    def detect_faces(self, image) -> list[ProviderFaceDetection]:
        boxes = _load_local_library().face_locations(image, model="hog")
        return [ProviderFaceDetection(tuple(box)) for box in boxes]

    def add_quality_input(self, image, detections):
        if not detections:
            return []
        library = _load_local_library()
        boxes = [detection.box for detection in detections]
        landmarks = library.face_landmarks(image, boxes)
        if len(landmarks) != len(detections):
            raise FaceImageError("Không thể trích xuất điểm đặc trưng khuôn mặt.")
        return [
            ProviderFaceDetection(detection.box, quality_input)
            for detection, quality_input in zip(detections, landmarks, strict=True)
        ]

    @staticmethod
    def scale_detection(detection: ProviderFaceDetection, factor: float):
        return ProviderFaceDetection(
            tuple(round(value * factor) for value in detection.box),
            {
                name: [(round(x * factor), round(y * factor)) for x, y in points]
                for name, points in detection.quality_input.items()
            },
        )

    @classmethod
    def supports_profile(cls, model_name: str | None, model_version: str | None) -> bool:
        return model_name == cls.name and model_version == cls.model_version

    @staticmethod
    def assess_enrollment_quality(_image, _detection) -> float:
        # Preserve the existing dlib enrollment behavior in this opt-in OpenCV change.
        return 1.0

    def create_embedding(self, image, detection):
        encodings = _load_local_library().face_encodings(
            image, known_face_locations=[detection.box]
        )
        if len(encodings) != 1:
            raise FaceImageError("Không thể trích xuất đặc trưng khuôn mặt từ ảnh.")
        return encodings[0]

    def compare_embeddings(self, known_embeddings, probe_embedding):
        library = _load_local_library()
        known_array = library.api.np.asarray(known_embeddings, dtype=float)
        probe_array = library.api.np.asarray(probe_embedding, dtype=float)
        return library.face_distance(known_array, probe_array)


class OpenCVFaceProvider:
    """YuNet + SFace ONNX provider, loaded only when explicitly selected."""

    name = "opencv-sface-128d"
    model_version = "2021dec"
    embedding_dimension = 128

    def __init__(
        self,
        *,
        cv2_module=None,
        yunet_path: Path | None = None,
        sface_path: Path | None = None,
        yunet_sha256: str | None = None,
        sface_sha256: str | None = None,
        confidence_threshold: float | None = None,
        nms_threshold: float | None = None,
        cosine_threshold: float | None = None,
    ):
        self.confidence_threshold = (
            settings.face_yunet_confidence_threshold
            if confidence_threshold is None else confidence_threshold
        )
        self.nms_threshold = (
            settings.face_yunet_nms_threshold if nms_threshold is None else nms_threshold
        )
        if not 0 < self.confidence_threshold <= 1 or not 0 < self.nms_threshold <= 1:
            raise FaceProviderUnavailable("Cấu hình threshold YuNet không hợp lệ.")
        self.cosine_threshold = (
            settings.face_sface_cosine_threshold
            if cosine_threshold is None else cosine_threshold
        )
        if self.cosine_threshold is None:
            raise FaceProviderUnavailable(
                "OpenCV FaceID thiếu threshold SFace đã được hiệu chỉnh."
            )
        if not -1 <= self.cosine_threshold <= 1:
            raise FaceProviderUnavailable("Cấu hình threshold SFace không hợp lệ.")
        self._yunet_path = self._validate_model(
            "YuNet",
            yunet_path or settings.face_yunet_model_path,
            yunet_sha256 or settings.face_yunet_model_sha256,
        )
        self._sface_path = self._validate_model(
            "SFace",
            sface_path or settings.face_sface_model_path,
            sface_sha256 or settings.face_sface_model_sha256,
        )
        self.cv = cv2_module or self._load_opencv()
        try:
            backend = self.cv.dnn.DNN_BACKEND_OPENCV
            target = self.cv.dnn.DNN_TARGET_CPU
            self.detector = self.cv.FaceDetectorYN.create(
                str(self._yunet_path), "", (320, 320), self.confidence_threshold,
                self.nms_threshold, 5000, backend, target
            )
            self.recognizer = self.cv.FaceRecognizerSF.create(
                str(self._sface_path), "", backend, target
            )
            # OpenCV DNN wrappers keep mutable inference state. The provider is
            # process-cached, so serialize calls shared by REST and kiosk streams.
            self._detector_lock = RLock()
            self._recognizer_lock = RLock()
        except Exception:
            raise FaceProviderUnavailable(
                "OpenCV FaceID không thể nạp model ONNX đã cấu hình."
            ) from None

    @staticmethod
    def _load_opencv():
        try:
            import cv2  # type: ignore[import-not-found]
        except (ImportError, SystemExit):
            raise FaceProviderUnavailable(
                "OpenCV FaceID chưa sẵn sàng. Hãy cài requirements-face-opencv.txt."
            ) from None
        if not hasattr(cv2, "FaceDetectorYN") or not hasattr(cv2, "FaceRecognizerSF"):
            raise FaceProviderUnavailable("Bản OpenCV hiện tại không hỗ trợ YuNet và SFace.")
        return cv2

    @staticmethod
    def _validate_model(label: str, path: Path | None, expected_sha256: str) -> Path:
        if path is None:
            raise FaceProviderUnavailable(f"OpenCV FaceID thiếu cấu hình model {label}.")
        candidate = Path(path).expanduser()
        if not candidate.is_absolute() or candidate.suffix.lower() != ".onnx" or not candidate.is_file():
            raise FaceProviderUnavailable(f"OpenCV FaceID model {label} không sẵn sàng.")
        try:
            digest_builder = sha256()
            with candidate.open("rb") as model_file:
                for chunk in iter(lambda: model_file.read(1024 * 1024), b""):
                    digest_builder.update(chunk)
            digest = digest_builder.hexdigest()
        except OSError:
            raise FaceProviderUnavailable(f"OpenCV FaceID model {label} không đọc được.") from None
        if not expected_sha256 or digest.lower() != expected_sha256.strip().lower():
            raise FaceProviderUnavailable(f"OpenCV FaceID model {label} không đúng checksum.")
        return candidate

    def _to_bgr(self, image):
        try:
            return self.cv.cvtColor(image, self.cv.COLOR_RGB2BGR)
        except Exception:
            raise InvalidFaceImageError("Ảnh khuôn mặt không hợp lệ.") from None

    def decode_image(self, image_path: Path):
        try:
            import numpy as np

            encoded = np.frombuffer(image_path.read_bytes(), dtype=np.uint8)
            image = self.cv.imdecode(encoded, self.cv.IMREAD_COLOR)
            if image is None:
                raise ValueError("decode failed")
            return self.cv.cvtColor(image, self.cv.COLOR_BGR2RGB)
        except Exception:
            raise InvalidFaceImageError("Ảnh khuôn mặt không hợp lệ.") from None

    def detect_faces(self, image) -> list[ProviderFaceDetection]:
        bgr = self._to_bgr(image)
        try:
            image_height, image_width = (int(value) for value in bgr.shape[:2])
        except (AttributeError, TypeError, ValueError):
            raise InvalidFaceImageError("Ảnh khuôn mặt không hợp lệ.") from None
        if image_width <= 0 or image_height <= 0:
            raise InvalidFaceImageError("Ảnh khuôn mặt không hợp lệ.")
        try:
            with self._detector_lock:
                self.detector.setInputSize((image_width, image_height))
                _status, faces = self.detector.detect(bgr)
        except Exception:
            raise FaceImageError("Không thể phát hiện khuôn mặt trong ảnh.") from None
        if faces is None:
            return []
        detections: list[ProviderFaceDetection] = []
        for row in faces:
            values = [float(value) for value in row]
            if len(values) != 15 or not all(math.isfinite(value) for value in values):
                raise FaceImageError("Kết quả phát hiện khuôn mặt không hợp lệ.")
            x, y, width, height = values[:4]
            if width <= 0 or height <= 0:
                raise FaceImageError("Kết quả phát hiện khuôn mặt không hợp lệ.")
            left = max(0, min(image_width, round(x)))
            top = max(0, min(image_height, round(y)))
            right = max(0, min(image_width, round(x + width)))
            bottom = max(0, min(image_height, round(y + height)))
            if right <= left or bottom <= top:
                raise FaceImageError("Kết quả phát hiện khuôn mặt không hợp lệ.")
            box = (top, right, bottom, left)
            quality_input = {
                "right_eye": [(round(values[4]), round(values[5]))],
                "left_eye": [(round(values[6]), round(values[7]))],
                "nose_tip": [(round(values[8]), round(values[9]))],
                "top_lip": [
                    (round(values[10]), round(values[11])),
                    (round(values[12]), round(values[13])),
                ],
            }
            detections.append(
                ProviderFaceDetection(box, quality_input, provider_input=tuple(values))
            )
        return sorted(detections, key=lambda detection: detection.box)

    def add_quality_input(self, image, detections):
        return list(detections)

    @staticmethod
    def scale_detection(detection: ProviderFaceDetection, factor: float):
        if factor == 1.0:
            return detection
        try:
            provider_values = tuple(
                float(value) * factor if index < 14 else float(value)
                for index, value in enumerate(detection.provider_input)
            )
        except (TypeError, ValueError):
            raise FaceImageError("Dữ liệu căn chỉnh khuôn mặt không hợp lệ.") from None
        return ProviderFaceDetection(
            tuple(round(value * factor) for value in detection.box),
            {
                name: [(round(x * factor), round(y * factor)) for x, y in points]
                for name, points in detection.quality_input.items()
            },
            provider_values,
        )

    def assess_enrollment_quality(self, image, detection: ProviderFaceDetection) -> float:
        """One-shot quality gate; realtime stability remains owned by the vision engine."""
        self._validate_alignment_input(detection)
        try:
            import numpy as np

            height, width = (int(value) for value in image.shape[:2])
            top, right, bottom, left = detection.box
            top, bottom = max(0, top), min(height, bottom)
            left, right = max(0, left), min(width, right)
            crop = np.asarray(image[top:bottom, left:right], dtype=np.float32)
            if crop.ndim != 3 or crop.shape[2] < 3 or crop.size == 0:
                raise ValueError("empty crop")
            gray = crop[:, :, :3].mean(axis=2)
            brightness = float(gray.mean())
            if gray.shape[0] < 3 or gray.shape[1] < 3:
                raise ValueError("small crop")
            laplacian = (
                -4 * gray[1:-1, 1:-1]
                + gray[:-2, 1:-1]
                + gray[2:, 1:-1]
                + gray[1:-1, :-2]
                + gray[1:-1, 2:]
            )
            blur_score = float(np.var(laplacian))
            right_eye = np.asarray(detection.quality_input["right_eye"][0], dtype=float)
            left_eye = np.asarray(detection.quality_input["left_eye"][0], dtype=float)
            nose = np.asarray(detection.quality_input["nose_tip"][0], dtype=float)
            eye_span = float(np.linalg.norm(left_eye - right_eye))
            midpoint = (left_eye + right_eye) / 2
            yaw_ratio = float(abs(nose[0] - midpoint[0]) / max(1.0, eye_span))
            roll_ratio = float(abs(left_eye[1] - right_eye[1]) / max(1.0, eye_span))
        except Exception:
            raise FaceImageError("Không thể đánh giá chất lượng khuôn mặt.") from None
        face_size = min(bottom - top, right - left)
        if (
            face_size < 160
            or brightness < 55
            or brightness > 205
            or blur_score < 75
            or eye_span <= 0
            or yaw_ratio >= 0.28
            or roll_ratio >= 0.16
        ):
            raise FaceImageError("Khuôn mặt chưa đạt yêu cầu chất lượng.")
        return 1.0

    @staticmethod
    def _validate_alignment_input(detection: ProviderFaceDetection):
        required_counts = {"right_eye": 1, "left_eye": 1, "nose_tip": 1, "top_lip": 2}
        if any(
            len(detection.quality_input.get(name, ())) != count
            for name, count in required_counts.items()
        ):
            raise FaceImageError("Thiếu landmark hợp lệ để căn chỉnh khuôn mặt.")
        try:
            landmark_values = [
                float(coordinate)
                for name in required_counts
                for point in detection.quality_input[name]
                for coordinate in point
            ]
        except (TypeError, ValueError):
            raise FaceImageError("Landmark căn chỉnh khuôn mặt không hợp lệ.") from None
        if len(landmark_values) != 10 or not all(
            math.isfinite(value) for value in landmark_values
        ):
            raise FaceImageError("Landmark căn chỉnh khuôn mặt không hợp lệ.")
        try:
            values = tuple(float(value) for value in detection.provider_input)
        except (TypeError, ValueError):
            raise FaceImageError("Thiếu dữ liệu căn chỉnh khuôn mặt từ YuNet.")
        if (
            len(values) != 15
            or not all(math.isfinite(value) for value in values)
            or values[2] <= 0
            or values[3] <= 0
        ):
            raise FaceImageError("Dữ liệu căn chỉnh khuôn mặt không hợp lệ.")
        return values

    def create_embedding(self, image, face):
        if not isinstance(face, QualityGatedFace):
            raise FaceImageError(
                "SFace chỉ tạo đặc trưng từ đúng một khuôn mặt đã qua quality gate."
            )
        alignment_input = self._validate_alignment_input(face.detection)
        try:
            import numpy as np

            bgr = self._to_bgr(image)
            face_row = np.asarray(alignment_input, dtype=np.float32)
            with self._recognizer_lock:
                aligned = self.recognizer.alignCrop(bgr, face_row)
                features = self.recognizer.feature(aligned)
            values = np.asarray(features, dtype=np.float32).reshape(-1)
            norm = float(np.linalg.norm(values))
        except Exception:
            raise FaceImageError("Không thể trích xuất đặc trưng khuôn mặt từ ảnh.") from None
        if (
            len(values) != self.embedding_dimension
            or not all(math.isfinite(float(value)) for value in values)
            or not math.isfinite(norm)
            or norm <= 0
        ):
            raise FaceImageError("Đặc trưng khuôn mặt không hợp lệ.")
        normalized = (values / norm).astype(np.float32, copy=False)
        normalized.setflags(write=False)
        return VersionedFaceEmbedding(
            model_name=self.name,
            model_version=self.model_version,
            dimension=self.embedding_dimension,
            values=normalized,
        )

    def _embedding_values(self, embedding: VersionedFaceEmbedding):
        if not isinstance(embedding, VersionedFaceEmbedding):
            raise FaceImageError("Đặc trưng khuôn mặt thiếu thông tin phiên bản.")
        if (
            embedding.model_name != self.name
            or embedding.model_version != self.model_version
            or embedding.dimension != self.embedding_dimension
        ):
            raise FaceImageError("Không thể so sánh đặc trưng từ model khác nhau.")
        try:
            import numpy as np

            values = np.asarray(embedding.values, dtype=np.float32).reshape(1, -1)
        except Exception:
            raise FaceImageError("Đặc trưng khuôn mặt không hợp lệ.") from None
        if values.shape[1] != self.embedding_dimension:
            raise FaceImageError("Đặc trưng khuôn mặt không hợp lệ.")
        norm = float(np.linalg.norm(values))
        if (
            not all(math.isfinite(float(value)) for value in values.reshape(-1))
            or not math.isfinite(norm)
            or abs(norm - 1.0) > 1e-4
        ):
            raise FaceImageError("Đặc trưng khuôn mặt không hợp lệ.")
        return values

    def compare_embeddings(self, known_embeddings, probe_embedding):
        try:
            probe = self._embedding_values(probe_embedding)
            similarities = []
            for known in known_embeddings:
                candidate = self._embedding_values(known)
                with self._recognizer_lock:
                    similarity = float(
                        self.recognizer.match(
                            candidate, probe, self.cv.FaceRecognizerSF_FR_COSINE
                        )
                    )
                if not math.isfinite(similarity):
                    raise FaceImageError("Kết quả so sánh khuôn mặt không hợp lệ.")
                similarities.append(similarity)
            return similarities
        except FaceImageError:
            raise
        except Exception:
            raise FaceImageError("Không thể so sánh đặc trưng khuôn mặt.") from None

    def is_match(self, cosine_similarity: float) -> bool:
        if not math.isfinite(cosine_similarity):
            raise FaceImageError("Kết quả so sánh khuôn mặt không hợp lệ.")
        return cosine_similarity >= self.cosine_threshold

    def supports_profile(self, model_name: str | None, model_version: str | None) -> bool:
        return model_name == self.name and model_version == self.model_version


def get_face_provider(provider_name: str | None = None) -> FaceProvider:
    selected = provider_name or settings.face_provider
    if selected == "local":
        return DlibFaceProvider()
    if selected == "local_opencv":
        return _get_opencv_provider(
            settings.face_yunet_model_path,
            settings.face_sface_model_path,
            settings.face_yunet_model_sha256,
            settings.face_sface_model_sha256,
            settings.face_yunet_confidence_threshold,
            settings.face_yunet_nms_threshold,
            settings.face_sface_cosine_threshold,
        )
    raise FaceProviderUnavailable(f"FaceID provider không được hỗ trợ: {selected}")


@lru_cache(maxsize=4)
def _get_opencv_provider(
    yunet_path: Path | None,
    sface_path: Path | None,
    yunet_sha256: str,
    sface_sha256: str,
    confidence_threshold: float,
    nms_threshold: float,
    cosine_threshold: float | None,
) -> OpenCVFaceProvider:
    return OpenCVFaceProvider(
        yunet_path=yunet_path,
        sface_path=sface_path,
        yunet_sha256=yunet_sha256,
        sface_sha256=sface_sha256,
        confidence_threshold=confidence_threshold,
        nms_threshold=nms_threshold,
        cosine_threshold=cosine_threshold,
    )


def _extract_single_encoding(image_path: Path):
    provider = get_face_provider("local")
    image = provider.decode_image(image_path)
    detections = provider.detect_faces(image)
    if not detections:
        raise NoFaceDetectedError("Không phát hiện khuôn mặt trong ảnh. Vui lòng nhìn thẳng vào camera.")
    if len(detections) > 1:
        raise MultipleFacesDetectedError(len(detections))
    return provider.create_embedding(image, detections[0])


class FaceService:
    @staticmethod
    def _serialize_embedding(values) -> bytes:
        try:
            serialized_values = [float(value) for value in values]
        except (TypeError, ValueError):
            raise FaceImageError("Đặc trưng khuôn mặt không hợp lệ.") from None
        if len(serialized_values) != 128 or not all(
            math.isfinite(value) for value in serialized_values
        ):
            raise FaceImageError("Đặc trưng khuôn mặt không hợp lệ.")
        return json.dumps(serialized_values).encode("utf-8")

    def prepare_enrollment(self, image_path: Path) -> FaceEnrollmentResult:
        """Finish all biometric work before the REST route touches persistent state."""
        if settings.face_provider == "mock":
            raise FaceProviderUnavailable(
                "FACE_PROVIDER=mock chỉ dành cho kiểm thử và không thể xác nhận danh tính thật. "
                "Đăng ký Face ID an toàn yêu cầu FACE_PROVIDER=local hoặc provider thật."
            )
        if settings.face_provider == "local":
            embedding = _extract_single_encoding(image_path)
            return FaceEnrollmentResult(
                None,
                self._serialize_embedding(embedding),
                DlibFaceProvider.name,
                DlibFaceProvider.model_version,
                1.0,
            )
        if settings.face_provider == "local_opencv":
            provider = get_face_provider("local_opencv")
            image = provider.decode_image(image_path)
            detections = provider.detect_faces(image)
            if not detections:
                raise NoFaceDetectedError(
                    "Không phát hiện khuôn mặt trong ảnh. Vui lòng nhìn thẳng vào camera."
                )
            if len(detections) > 1:
                raise MultipleFacesDetectedError(len(detections))
            detections = provider.add_quality_input(image, detections)
            if len(detections) != 1:
                raise FaceImageError("Kết quả phát hiện khuôn mặt không nhất quán.")
            quality_score = provider.assess_enrollment_quality(image, detections[0])
            if (
                not isinstance(quality_score, (int, float))
                or not math.isfinite(float(quality_score))
                or not 0 <= float(quality_score) <= 1
            ):
                raise FaceImageError("Kết quả đánh giá chất lượng khuôn mặt không hợp lệ.")
            gated_face = QualityGatedFace.from_detections(
                detections, quality_accepted=True
            )
            embedding = provider.create_embedding(image, gated_face)
            if not isinstance(embedding, VersionedFaceEmbedding):
                raise FaceImageError("Đặc trưng khuôn mặt thiếu thông tin phiên bản.")
            if not provider.supports_profile(embedding.model_name, embedding.model_version):
                raise FaceImageError("Đặc trưng khuôn mặt không tương thích provider.")
            return FaceEnrollmentResult(
                None,
                self._serialize_embedding(embedding.values),
                embedding.model_name,
                embedding.model_version,
                float(quality_score),
            )
        raise FaceProviderUnavailable(
            f"FaceID provider không được hỗ trợ: {settings.face_provider}"
        )

    def validate_enrollment_image(self, image_path: Path):
        """Detect once before any user/profile mutation and return the gated encoding.

        Mock has no detector and therefore cannot make a safe biometric enrollment
        claim. It stays available for isolated service/UI tests only.
        """
        if settings.face_provider == "local":
            return _extract_single_encoding(image_path)
        return self.prepare_enrollment(image_path)

    def enroll_face(self, user_id: UUID, image_path: Path, validated_encoding=None) -> FaceEnrollmentResult:
        if settings.face_provider == "local":
            encoding = validated_encoding if validated_encoding is not None else _extract_single_encoding(image_path)
            serialized = self._serialize_embedding(encoding)
            return FaceEnrollmentResult(
                None, serialized, DlibFaceProvider.name, DlibFaceProvider.model_version, 1.0
            )
        if settings.face_provider == "local_opencv":
            if isinstance(validated_encoding, FaceEnrollmentResult):
                return validated_encoding
            return self.prepare_enrollment(image_path)
        if settings.face_provider == "mock":
            digest = sha256(image_path.read_bytes()).hexdigest()
            return FaceEnrollmentResult(
                f"mock://face/{user_id}/{digest}", None, "mock-face-v1", "1", 0.95
            )
        raise FaceProviderUnavailable(
            f"FaceID provider không được hỗ trợ: {settings.face_provider}"
        )

    def verify_face(
        self,
        image_path: Path,
        candidates: Iterable[FaceCandidate | VersionedFaceCandidate] | UUID | None,
    ) -> FaceVerificationResult:
        # UUID/None compatibility keeps the Phase 3 service boundary usable.
        if isinstance(candidates, UUID):
            candidate_list: list[FaceCandidate | VersionedFaceCandidate] = [
                (candidates, None, None)
            ]
        elif candidates is None:
            candidate_list = []
        else:
            candidate_list = list(candidates)
        if settings.face_provider == "local":
            probe = _extract_single_encoding(image_path)
            compatible = [candidate[:3] for candidate in candidate_list if len(candidate) == 3 or (
                candidate[3] == DlibFaceProvider.name
                and candidate[4] == DlibFaceProvider.model_version
            )]
            return self.verify_encoding(probe, compatible)

        if settings.face_provider == "local_opencv":
            provider = get_face_provider("local_opencv")
            image = provider.decode_image(image_path)
            detections = provider.add_quality_input(image, provider.detect_faces(image))
            gated = QualityGatedFace.from_detections(detections, quality_accepted=True)
            provider.assess_enrollment_quality(image, gated.detection)
            probe = provider.create_embedding(image, gated)
            gallery: list[tuple[UUID, VersionedFaceEmbedding]] = []
            for candidate in candidate_list:
                if len(candidate) != 5:
                    continue
                user_id, template_bytes, _template_ref, model_name, model_version = candidate
                if not template_bytes or not provider.supports_profile(model_name, model_version):
                    continue
                try:
                    values = [
                        float(value)
                        for value in json.loads(template_bytes.decode("utf-8"))
                    ]
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
                    VersionedFaceEmbedding(
                        model_name, model_version, len(values), values
                    ),
                ))
            if not gallery:
                return FaceVerificationResult(
                    "UNKNOWN_FACE", None, None,
                    embedding_dimension=probe.dimension,
                    embedding_norm=1.0,
                )
            similarities = provider.compare_embeddings(
                [embedding for _user_id, embedding in gallery], probe
            )
            best_index = max(
                range(len(similarities)), key=lambda index: float(similarities[index])
            )
            similarity = float(similarities[best_index])
            matched = provider.is_match(similarity)
            return FaceVerificationResult(
                "SUCCESS" if matched else "UNKNOWN_FACE",
                gallery[best_index][0] if matched else None,
                max(0.0, min(1.0, similarity)),
                distance=1.0 - similarity,
                embedding_dimension=probe.dimension,
                embedding_norm=1.0,
            )

        if settings.face_provider != "mock":
            raise FaceProviderUnavailable(
                "OpenCV FaceID chưa được bật cho recognition trong bước chuẩn bị này."
            )

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
        return self.verify_prepared_encoding(
            probe, self.prepare_candidates(candidates), provider=get_face_provider("local")
        )

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

    def verify_prepared_encoding(self, probe, prepared, provider: FaceProvider | None = None) -> FaceVerificationResult:
        # Direct callers of this legacy dlib matcher retain their old behavior.
        # Realtime/provider-aware callers pass the selected provider explicitly.
        provider = provider or get_face_provider("local")
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
        distances = provider.compare_embeddings(known_encodings, probe_values)
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
