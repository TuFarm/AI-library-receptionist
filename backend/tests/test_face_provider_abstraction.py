from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import face_service
from app.services.face_service import (
    DlibFaceProvider,
    FaceImageError,
    FaceProviderUnavailable,
    InvalidFaceImageError,
    ProviderFaceDetection,
    get_face_provider,
)
from app.vision.image_decoder import ImageDecoder, InvalidImageError


class FakeArray:
    shape = (200, 300, 3)


class FakeNumpy:
    @staticmethod
    def asarray(values, dtype=None):
        return values


class FakeDlibLibrary:
    api = SimpleNamespace(np=FakeNumpy())

    @staticmethod
    def load_image_file(path):
        return {"path": path}

    @staticmethod
    def face_locations(_image, model="hog"):
        assert model == "hog"
        return [(10, 110, 120, 5)]

    @staticmethod
    def face_landmarks(_image, boxes):
        assert boxes == [(10, 110, 120, 5)]
        return [{"left_eye": [(20, 30)], "right_eye": [(70, 30)]}]

    @staticmethod
    def face_encodings(_image, known_face_locations):
        assert known_face_locations == [(10, 110, 120, 5)]
        return [[0.1] * 128]

    @staticmethod
    def face_distance(known, probe):
        assert len(known[0]) == len(probe) == 128
        return [0.42]


def test_local_factory_exposes_separate_current_provider_tasks(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(face_service, "_load_local_library", lambda: FakeDlibLibrary())
    provider = get_face_provider("local")
    assert isinstance(provider, DlibFaceProvider)

    image_path = tmp_path / "face.jpg"
    image = provider.decode_image(image_path)
    detections = provider.detect_faces(image)
    assert detections == [ProviderFaceDetection((10, 110, 120, 5))]

    detections = provider.add_quality_input(image, detections)
    assert detections[0].quality_input["left_eye"] == [(20, 30)]
    embedding = provider.create_embedding(image, detections[0])
    assert len(embedding) == 128
    assert list(provider.compare_embeddings([embedding], embedding)) == [0.42]


def test_embedding_failure_is_normalized_as_face_image_error(monkeypatch):
    class NoEmbeddingLibrary(FakeDlibLibrary):
        @staticmethod
        def face_encodings(_image, known_face_locations):
            return []

    monkeypatch.setattr(face_service, "_load_local_library", lambda: NoEmbeddingLibrary())
    with pytest.raises(FaceImageError, match="trích xuất đặc trưng"):
        DlibFaceProvider().create_embedding(FakeArray(), ProviderFaceDetection((10, 110, 120, 5)))


def test_provider_decode_failure_is_normalized_as_invalid_image(monkeypatch, tmp_path: Path):
    class InvalidImageLibrary(FakeDlibLibrary):
        @staticmethod
        def load_image_file(_path):
            raise OSError("decoder details must not escape")

    monkeypatch.setattr(face_service, "_load_local_library", lambda: InvalidImageLibrary())
    with pytest.raises(InvalidFaceImageError, match="không hợp lệ"):
        DlibFaceProvider().decode_image(tmp_path / "invalid.jpg")


def test_unknown_provider_is_normalized_as_provider_unavailable():
    with pytest.raises(FaceProviderUnavailable, match="không được hỗ trợ"):
        get_face_provider("opencv_sface")


def test_websocket_decoder_normalizes_invalid_image_data():
    with pytest.raises(InvalidImageError, match="Invalid image data"):
        ImageDecoder().decode(b"not-an-image")
