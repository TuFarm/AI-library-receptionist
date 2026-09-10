from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import sleep

import pytest

from app.services.face_service import (
    FaceImageError,
    InvalidFaceImageError,
    OpenCVFaceProvider,
)


class FakeImage:
    shape = (480, 640, 3)


class FakeDetector:
    def __init__(self, faces):
        self.faces = faces
        self.input_sizes = []

    def setInputSize(self, size):
        self.input_sizes.append(size)

    def detect(self, _image):
        return 1, self.faces


class FakeFactory:
    def __init__(self, result):
        self.result = result

    def create(self, *_args):
        return self.result


def model(tmp_path: Path, name: str, content: bytes):
    path = tmp_path / name
    path.write_bytes(content)
    return path, sha256(content).hexdigest()


def provider(tmp_path: Path, faces):
    yunet, yunet_hash = model(tmp_path, "yunet.onnx", b"reviewed-yunet")
    sface, sface_hash = model(tmp_path, "sface.onnx", b"reviewed-sface")
    detector = FakeDetector(faces)
    cv = SimpleNamespace(
        dnn=SimpleNamespace(DNN_BACKEND_OPENCV=3, DNN_TARGET_CPU=0),
        FaceDetectorYN=FakeFactory(detector),
        FaceRecognizerSF=FakeFactory(object()),
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
        cosine_threshold=0.5,
    ), detector


def face_row(x=20, y=30, width=100, height=120, score=0.97):
    return [
        x, y, width, height,
        x + 30, y + 40,
        x + 70, y + 40,
        x + 50, y + 65,
        x + 35, y + 95,
        x + 65, y + 95,
        score,
    ]


def test_yunet_no_face_returns_zero_and_uses_actual_image_size(tmp_path: Path):
    face_provider, detector = provider(tmp_path, None)
    detections = face_provider.detect_faces(FakeImage())
    assert len(detections) == 0
    assert detector.input_sizes == [(640, 480)]


def test_yunet_one_face_returns_internal_box_and_landmarks_without_embedding(tmp_path: Path):
    face_provider, _detector = provider(tmp_path, [face_row()])
    detections = face_provider.detect_faces(FakeImage())
    assert len(detections) == 1
    detection = detections[0]
    assert detection.box == (30, 120, 150, 20)
    assert set(detection.quality_input) == {"right_eye", "left_eye", "nose_tip", "top_lip"}
    assert detection.provider_input[-1] == 0.97
    assert not hasattr(detection, "embedding")
    assert "30" not in repr(detection)
    assert "right_eye" not in repr(detection)


def test_yunet_multiple_faces_returns_every_face_in_stable_order(tmp_path: Path):
    face_provider, _detector = provider(
        tmp_path, [face_row(x=300, y=40), face_row(x=10, y=20), face_row(x=150, y=30)]
    )
    detections = face_provider.detect_faces(FakeImage())
    assert len(detections) >= 2
    assert [detection.box for detection in detections] == sorted(
        detection.box for detection in detections
    )


def test_yunet_decode_error_is_safe(tmp_path: Path):
    face_provider, _detector = provider(tmp_path, None)
    face_provider.cv.imdecode = lambda *_args: None
    invalid = tmp_path / "invalid.jpg"
    invalid.write_bytes(b"not-an-image")
    with pytest.raises(InvalidFaceImageError, match="không hợp lệ") as captured:
        face_provider.decode_image(invalid)
    assert str(invalid) not in str(captured.value)


def test_yunet_rejects_malformed_detection_rows(tmp_path: Path):
    face_provider, _detector = provider(tmp_path, [[1, 2, 3]])
    with pytest.raises(FaceImageError, match="Kết quả phát hiện"):
        face_provider.detect_faces(FakeImage())


def test_yunet_detector_does_not_write_face_data_to_logs(tmp_path: Path, caplog):
    face_provider, _detector = provider(tmp_path, [face_row()])
    face_provider.detect_faces(FakeImage())
    assert caplog.records == []


def test_shared_yunet_detector_serializes_concurrent_inference(tmp_path: Path):
    class ConcurrentDetector(FakeDetector):
        def __init__(self):
            super().__init__(None)
            self.active = 0
            self.maximum_active = 0
            self.guard = Lock()

        def detect(self, _image):
            with self.guard:
                self.active += 1
                self.maximum_active = max(self.maximum_active, self.active)
            sleep(0.01)
            with self.guard:
                self.active -= 1
            return 1, None

    face_provider, _unused = provider(tmp_path, None)
    detector = ConcurrentDetector()
    face_provider.detector = detector
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(face_provider.detect_faces, [FakeImage()] * 8)) == [[]] * 8
    assert detector.maximum_active == 1
