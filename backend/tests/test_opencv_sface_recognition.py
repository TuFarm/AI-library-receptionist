from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import sleep

import numpy as np
import pytest

from app.services.face_service import (
    FaceImageError,
    FaceProviderUnavailable,
    FaceService,
    MultipleFacesDetectedError,
    NoFaceDetectedError,
    OpenCVFaceProvider,
    ProviderFaceDetection,
    QualityGatedFace,
    VersionedFaceEmbedding,
)
from app.vision.recognition_service import RecognitionService


class FakeImage:
    shape = (480, 640, 3)


class FakeDetector:
    def setInputSize(self, _size):
        pass

    def detect(self, _image):
        return 1, None


class FakeRecognizer:
    def __init__(self, features=None):
        self.features = np.asarray(
            features if features is not None else np.arange(1, 129), dtype=np.float32
        ).reshape(1, -1)
        self.align_calls = []
        self.feature_calls = []
        self.match_calls = []

    def alignCrop(self, image, face_row):
        self.align_calls.append((image, face_row.copy()))
        return object()

    def feature(self, aligned):
        self.feature_calls.append(aligned)
        return self.features

    def match(self, candidate, probe, metric):
        self.match_calls.append((candidate, probe, metric))
        return float(np.sum(candidate * probe))


class FakeFactory:
    def __init__(self, result):
        self.result = result

    def create(self, *_args):
        return self.result


def _model(tmp_path: Path, name: str, content: bytes):
    path = tmp_path / name
    path.write_bytes(content)
    return path, sha256(content).hexdigest()


def _provider(tmp_path: Path, recognizer=None, *, cosine_threshold=0.5):
    yunet, yunet_hash = _model(tmp_path, "yunet.onnx", b"reviewed-yunet")
    sface, sface_hash = _model(tmp_path, "sface.onnx", b"reviewed-sface")
    recognizer = recognizer or FakeRecognizer()
    cv = SimpleNamespace(
        dnn=SimpleNamespace(DNN_BACKEND_OPENCV=3, DNN_TARGET_CPU=0),
        FaceDetectorYN=FakeFactory(FakeDetector()),
        FaceRecognizerSF=FakeFactory(recognizer),
        FaceRecognizerSF_FR_COSINE=0,
        COLOR_RGB2BGR=1,
        COLOR_BGR2RGB=2,
        IMREAD_COLOR=1,
        cvtColor=lambda image, _conversion: image,
    )
    return OpenCVFaceProvider(
        cv2_module=cv,
        yunet_path=yunet,
        sface_path=sface,
        yunet_sha256=yunet_hash,
        sface_sha256=sface_hash,
        cosine_threshold=cosine_threshold,
    ), recognizer


def _detection():
    row = (
        20.0, 30.0, 100.0, 120.0,
        50.0, 70.0, 90.0, 70.0, 70.0, 95.0,
        55.0, 125.0, 85.0, 125.0, 0.97,
    )
    quality_input = {
        "right_eye": [(50, 70)],
        "left_eye": [(90, 70)],
        "nose_tip": [(70, 95)],
        "top_lip": [(55, 125), (85, 125)],
    }
    return ProviderFaceDetection((30, 120, 150, 20), quality_input, row)


def _embedding(values, *, model_name="opencv-sface-128d", model_version="2021dec"):
    values = np.asarray(values, dtype=np.float32)
    values = values / np.linalg.norm(values)
    return VersionedFaceEmbedding(model_name, model_version, 128, values)


def test_exact_one_face_gate_rejects_zero_and_multiple_before_sface(tmp_path: Path):
    provider, recognizer = _provider(tmp_path)
    with pytest.raises(NoFaceDetectedError):
        QualityGatedFace.from_detections([], quality_accepted=True)
    with pytest.raises(MultipleFacesDetectedError) as captured:
        QualityGatedFace.from_detections(
            [_detection(), _detection()], quality_accepted=True
        )
    assert captured.value.face_count == 2
    assert recognizer.align_calls == []
    assert provider.embedding_dimension == 128


def test_quality_gate_and_raw_detection_cannot_reach_sface(tmp_path: Path):
    provider, recognizer = _provider(tmp_path)
    with pytest.raises(FaceImageError, match="chất lượng"):
        QualityGatedFace.from_detections([_detection()], quality_accepted=False)
    with pytest.raises(FaceImageError, match="quality gate"):
        provider.create_embedding(FakeImage(), _detection())
    assert recognizer.align_calls == []


def test_sface_aligns_then_returns_normalized_versioned_float32_embedding(tmp_path: Path):
    provider, recognizer = _provider(tmp_path)
    gated = QualityGatedFace.from_detections([_detection()], quality_accepted=True)
    embedding = provider.create_embedding(FakeImage(), gated)

    assert len(recognizer.align_calls) == 1
    assert recognizer.align_calls[0][1].shape == (15,)
    assert len(recognizer.feature_calls) == 1
    assert embedding.model_name == "opencv-sface-128d"
    assert embedding.model_version == "2021dec"
    assert embedding.dimension == 128
    assert embedding.values.dtype == np.float32
    assert np.linalg.norm(embedding.values) == pytest.approx(1.0)
    assert embedding.values.flags.writeable is False
    assert "values=<redacted>" in repr(embedding)
    assert "0.97" not in repr(gated)


def test_sface_rejects_invalid_landmarks_before_alignment(tmp_path: Path):
    provider, recognizer = _provider(tmp_path)
    invalid = ProviderFaceDetection((30, 120, 150, 20), {}, (1.0,) * 15)
    gated = QualityGatedFace.from_detections([invalid], quality_accepted=True)
    with pytest.raises(FaceImageError, match="landmark"):
        provider.create_embedding(FakeImage(), gated)
    assert recognizer.align_calls == []


def test_sface_rejects_non_finite_landmarks_before_alignment(tmp_path: Path):
    provider, recognizer = _provider(tmp_path)
    detection = _detection()
    quality_input = dict(detection.quality_input)
    quality_input["nose_tip"] = [(float("nan"), 95)]
    invalid = ProviderFaceDetection(detection.box, quality_input, detection.provider_input)
    gated = QualityGatedFace.from_detections([invalid], quality_accepted=True)
    with pytest.raises(FaceImageError, match="Landmark"):
        provider.create_embedding(FakeImage(), gated)
    assert recognizer.align_calls == []


def test_opencv_static_enrollment_quality_gate_accepts_sharp_face_and_rejects_blur(
    tmp_path: Path
):
    provider, _recognizer = _provider(tmp_path)
    checkerboard = (
        (np.indices((300, 300)).sum(axis=0) % 2)[:, :, None]
        * np.ones((1, 1, 3))
        * 200
    ).astype(np.uint8)
    detection = _detection()
    large_detection = ProviderFaceDetection(
        (30, 250, 250, 20),
        detection.quality_input,
        (20.0, 30.0, 230.0, 220.0, *detection.provider_input[4:]),
    )
    assert provider.assess_enrollment_quality(checkerboard, large_detection) == 1.0

    flat = np.full((300, 300, 3), 100, dtype=np.uint8)
    with pytest.raises(FaceImageError, match="chất lượng"):
        provider.assess_enrollment_quality(flat, large_detection)


@pytest.mark.parametrize("features", [[0.0] * 128, [float("nan")] * 128, [1.0] * 127])
def test_sface_rejects_invalid_embedding_output(tmp_path: Path, features):
    provider, _recognizer = _provider(tmp_path, FakeRecognizer(features))
    gated = QualityGatedFace.from_detections([_detection()], quality_accepted=True)
    with pytest.raises(FaceImageError, match="Đặc trưng"):
        provider.create_embedding(FakeImage(), gated)


def test_sface_matching_uses_cosine_and_configured_threshold(tmp_path: Path):
    provider, recognizer = _provider(tmp_path, cosine_threshold=0.75)
    probe = _embedding([1.0] + [0.0] * 127)
    same = _embedding([1.0] + [0.0] * 127)
    orthogonal = _embedding([0.0, 1.0] + [0.0] * 126)

    similarities = provider.compare_embeddings([same, orthogonal], probe)
    assert similarities == pytest.approx([1.0, 0.0])
    assert [call[2] for call in recognizer.match_calls] == [0, 0]
    assert provider.is_match(similarities[0]) is True
    assert provider.is_match(similarities[1]) is False


def test_sface_never_compares_dlib_or_different_version_templates(tmp_path: Path):
    provider, recognizer = _provider(tmp_path)
    probe = _embedding([1.0] * 128)
    dlib = _embedding([1.0] * 128, model_name="face-recognition-hog-128d", model_version="1")
    with pytest.raises(FaceImageError, match="model khác nhau"):
        provider.compare_embeddings([dlib], probe)
    assert provider.supports_profile("face-recognition-hog-128d", "1") is False
    assert provider.supports_profile("opencv-sface-128d", "2021dec") is True
    assert recognizer.match_calls == []


def test_sface_identity_decision_fails_closed_without_calibrated_threshold(
    tmp_path: Path, monkeypatch
):
    from app.services import face_service

    monkeypatch.setattr(face_service.settings, "face_sface_cosine_threshold", None)
    with pytest.raises(FaceProviderUnavailable, match="threshold"):
        _provider(tmp_path, cosine_threshold=None)


def test_sface_does_not_log_landmarks_or_embeddings(tmp_path: Path, caplog):
    provider, _recognizer = _provider(tmp_path)
    gated = QualityGatedFace.from_detections([_detection()], quality_accepted=True)
    provider.create_embedding(FakeImage(), gated)
    assert caplog.records == []


def test_shared_sface_recognizer_serializes_concurrent_inference(tmp_path: Path):
    class ConcurrentRecognizer(FakeRecognizer):
        def __init__(self):
            super().__init__()
            self.active = 0
            self.maximum_active = 0
            self.guard = Lock()

        def alignCrop(self, image, face_row):
            with self.guard:
                self.active += 1
                self.maximum_active = max(self.maximum_active, self.active)
            sleep(0.01)
            return super().alignCrop(image, face_row)

        def feature(self, aligned):
            result = super().feature(aligned)
            with self.guard:
                self.active -= 1
            return result

    recognizer = ConcurrentRecognizer()
    provider, _unused = _provider(tmp_path, recognizer)
    gated = QualityGatedFace.from_detections([_detection()], quality_accepted=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        embeddings = list(pool.map(lambda _index: provider.create_embedding(FakeImage(), gated), range(8)))
    assert len(embeddings) == 8
    assert recognizer.maximum_active == 1


def test_realtime_opencv_recognition_uses_one_quality_detection_and_versioned_gallery(
    monkeypatch, tmp_path: Path
):
    from app.vision import recognition_service

    provider, _recognizer = _provider(tmp_path, cosine_threshold=0.5)
    monkeypatch.setattr(recognition_service, "get_face_provider", lambda: provider)
    expected = np.arange(1, 129, dtype=np.float32)
    expected /= np.linalg.norm(expected)
    user_id = UUID("aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa")
    candidates = [(
        user_id,
        json.dumps([float(value) for value in expected]).encode(),
        None,
        "opencv-sface-128d",
        "2021dec",
    )]

    result = RecognitionService().recognize(
        FakeImage(), [_detection()], candidates, quality_accepted=True
    )
    assert result.result == "SUCCESS"
    assert result.user_id == user_id


def test_realtime_recognition_rejects_multiple_or_unqualified_faces_before_sface(
    monkeypatch, tmp_path: Path
):
    from app.vision import recognition_service

    provider, recognizer = _provider(tmp_path, cosine_threshold=0.5)
    monkeypatch.setattr(recognition_service, "get_face_provider", lambda: provider)
    service = RecognitionService()
    with pytest.raises(MultipleFacesDetectedError):
        service.recognize(FakeImage(), [_detection(), _detection()], [], True)
    with pytest.raises(FaceImageError, match="chất lượng"):
        service.recognize(FakeImage(), [_detection()], [], False)
    assert recognizer.align_calls == []


def test_realtime_opencv_gallery_ignores_dlib_profile(monkeypatch, tmp_path: Path):
    from app.vision import recognition_service

    provider, recognizer = _provider(tmp_path, cosine_threshold=0.5)
    monkeypatch.setattr(recognition_service, "get_face_provider", lambda: provider)
    dlib_candidate = (
        UUID("bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb"),
        json.dumps([0.1] * 128).encode(),
        None,
        "face-recognition-hog-128d",
        "1",
    )
    result = RecognitionService().recognize(
        FakeImage(), [_detection()], [dlib_candidate], quality_accepted=True
    )
    assert result.result == "UNKNOWN_FACE"
    assert result.user_id is None
    assert recognizer.match_calls == []


def test_realtime_gallery_expires_for_profile_refresh(monkeypatch):
    from app.vision import recognition_service

    monkeypatch.setattr(recognition_service.settings, "face_gallery_ttl_ms", 5000)
    service = RecognitionService()
    assert service.gallery_expired(10.0) is True
    service.refresh_gallery(10.0)
    assert service.gallery_expired(14.999) is False
    assert service.gallery_expired(15.0) is True


def test_rest_service_opencv_verification_filters_versions_and_matches(
    monkeypatch, tmp_path: Path
):
    from app.services import face_service

    provider, _recognizer = _provider(tmp_path, cosine_threshold=0.5)
    provider.decode_image = lambda _path: FakeImage()
    provider.detect_faces = lambda _image: [_detection()]
    provider.assess_enrollment_quality = lambda _image, _detection: 1.0
    monkeypatch.setattr(face_service.settings, "face_provider", "local_opencv")
    monkeypatch.setattr(face_service, "get_face_provider", lambda _name=None: provider)
    expected = np.arange(1, 129, dtype=np.float32)
    expected /= np.linalg.norm(expected)
    user_id = UUID("aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa")
    candidates = [
        (UUID("bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb"), b"[]", None,
         "face-recognition-hog-128d", "1"),
        (user_id, json.dumps([float(value) for value in expected]).encode(), None,
         "opencv-sface-128d", "2021dec"),
    ]
    result = FaceService().verify_face(tmp_path / "not-read-by-fake.jpg", candidates)
    assert result.result == "SUCCESS"
    assert result.user_id == user_id


@pytest.mark.parametrize("face_count", [0, 2])
def test_rest_service_opencv_verification_requires_exactly_one_face(
    monkeypatch, tmp_path: Path, face_count: int
):
    from app.services import face_service

    provider, recognizer = _provider(tmp_path, cosine_threshold=0.5)
    provider.decode_image = lambda _path: FakeImage()
    provider.detect_faces = lambda _image: [_detection()] * face_count
    monkeypatch.setattr(face_service.settings, "face_provider", "local_opencv")
    monkeypatch.setattr(face_service, "get_face_provider", lambda _name=None: provider)
    expected_error = NoFaceDetectedError if face_count == 0 else MultipleFacesDetectedError
    with pytest.raises(expected_error):
        FaceService().verify_face(tmp_path / "not-read-by-fake.jpg", [])
    assert recognizer.align_calls == []
