from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.services.face_service import FaceProviderUnavailable, FaceService, OpenCVFaceProvider


class FakeFactory:
    def __init__(self, result=None, error: Exception | None = None):
        self.calls = []
        self.result = result or object()
        self.error = error

    def create(self, *args):
        self.calls.append(args)
        if self.error:
            raise self.error
        return self.result


def fake_cv(detector_factory=None, recognizer_factory=None):
    return SimpleNamespace(
        dnn=SimpleNamespace(DNN_BACKEND_OPENCV=3, DNN_TARGET_CPU=0),
        FaceDetectorYN=detector_factory or FakeFactory(),
        FaceRecognizerSF=recognizer_factory or FakeFactory(),
        COLOR_RGB2BGR=1,
        COLOR_BGR2RGB=2,
        IMREAD_COLOR=1,
        cvtColor=lambda image, _conversion: image,
    )


def model(tmp_path: Path, name: str, content: bytes):
    path = tmp_path / name
    path.write_bytes(content)
    return path, sha256(content).hexdigest()


def test_opencv_config_is_opt_in_and_has_pinned_model_identities():
    configured = Settings(_env_file=None)
    assert configured.face_provider == "mock"
    assert configured.face_yunet_model_path is None
    assert configured.face_sface_model_path is None
    assert len(configured.face_yunet_model_sha256) == 64
    assert len(configured.face_sface_model_sha256) == 64
    assert configured.face_yunet_confidence_threshold == 0.9
    assert configured.face_yunet_nms_threshold == 0.3
    assert configured.face_sface_cosine_threshold is None
    assert configured.face_analysis_width == 640
    assert configured.face_frame_interval_ms == 100
    assert configured.face_recognition_cadence_ms == 500


@pytest.mark.parametrize("threshold", [-1.01, 1.01])
def test_sface_cosine_threshold_config_rejects_out_of_range_values(threshold: float):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, face_sface_cosine_threshold=threshold)


def test_provider_validates_files_and_uses_opencv_dnn_factories(tmp_path: Path):
    yunet, yunet_hash = model(tmp_path, "yunet.onnx", b"reviewed-yunet")
    sface, sface_hash = model(tmp_path, "sface.onnx", b"reviewed-sface")
    detector_factory = FakeFactory()
    recognizer_factory = FakeFactory()
    provider = OpenCVFaceProvider(
        cv2_module=fake_cv(detector_factory, recognizer_factory),
        yunet_path=yunet,
        sface_path=sface,
        yunet_sha256=yunet_hash,
        sface_sha256=sface_hash,
        cosine_threshold=0.5,
    )
    assert provider.detector is detector_factory.result
    assert provider.recognizer is recognizer_factory.result
    assert detector_factory.calls[0][2] == (320, 320)
    assert detector_factory.calls[0][3:6] == (0.9, 0.3, 5000)
    assert recognizer_factory.calls[0][-2:] == (3, 0)


@pytest.mark.parametrize("missing", ["yunet", "sface"])
def test_missing_model_fails_closed_without_exposing_path(tmp_path: Path, missing: str):
    present, digest = model(tmp_path, "present.onnx", b"reviewed")
    secret = tmp_path / "private" / "missing.onnx"
    values = {
        "yunet_path": secret if missing == "yunet" else present,
        "sface_path": secret if missing == "sface" else present,
        "yunet_sha256": digest,
        "sface_sha256": digest,
    }
    with pytest.raises(FaceProviderUnavailable) as captured:
        OpenCVFaceProvider(cv2_module=fake_cv(), cosine_threshold=0.5, **values)
    assert str(secret) not in str(captured.value)
    assert {"yunet": "YuNet", "sface": "SFace"}[missing] in str(captured.value)


def test_wrong_extension_or_checksum_fails_before_opencv_load(tmp_path: Path):
    wrong_type, digest = model(tmp_path, "yunet.bin", b"reviewed")
    sface, sface_hash = model(tmp_path, "sface.onnx", b"reviewed-sface")
    with pytest.raises(FaceProviderUnavailable, match="YuNet.*không sẵn sàng"):
        OpenCVFaceProvider(
            cv2_module=fake_cv(), yunet_path=wrong_type, sface_path=sface,
            yunet_sha256=digest, sface_sha256=sface_hash, cosine_threshold=0.5,
        )
    yunet, _yunet_hash = model(tmp_path, "yunet.onnx", b"reviewed-yunet")
    with pytest.raises(FaceProviderUnavailable, match="YuNet.*checksum"):
        OpenCVFaceProvider(
            cv2_module=fake_cv(), yunet_path=yunet, sface_path=sface,
            yunet_sha256="0" * 64, sface_sha256=sface_hash, cosine_threshold=0.5,
        )


def test_model_paths_must_be_absolute(monkeypatch, tmp_path: Path):
    yunet, yunet_hash = model(tmp_path, "yunet.onnx", b"reviewed-yunet")
    sface, sface_hash = model(tmp_path, "sface.onnx", b"reviewed-sface")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FaceProviderUnavailable, match="YuNet.*không sẵn sàng"):
        OpenCVFaceProvider(
            cv2_module=fake_cv(), yunet_path=Path(yunet.name), sface_path=sface,
            yunet_sha256=yunet_hash, sface_sha256=sface_hash, cosine_threshold=0.5,
        )


def test_opencv_parse_failure_is_safe_and_does_not_fallback(tmp_path: Path):
    yunet, yunet_hash = model(tmp_path, "yunet.onnx", b"reviewed-yunet")
    sface, sface_hash = model(tmp_path, "sface.onnx", b"reviewed-sface")
    detector_factory = FakeFactory(error=RuntimeError("private parser details"))
    with pytest.raises(FaceProviderUnavailable, match="không thể nạp model ONNX") as captured:
        OpenCVFaceProvider(
            cv2_module=fake_cv(detector_factory=detector_factory),
            yunet_path=yunet,
            sface_path=sface,
            yunet_sha256=yunet_hash,
            sface_sha256=sface_hash,
            cosine_threshold=0.5,
        )
    assert "private parser details" not in str(captured.value)


def test_app_startup_validates_only_explicit_opencv_provider(monkeypatch):
    from app import main

    calls = []
    monkeypatch.setattr(main, "get_face_provider", lambda name: calls.append(name) or object())
    monkeypatch.setattr(main.settings, "face_provider", "mock")
    main.create_app()
    assert calls == []
    monkeypatch.setattr(main.settings, "face_provider", "local_opencv")
    main.create_app()
    assert calls == ["local_opencv"]


def test_provider_fails_creation_without_calibrated_sface_threshold(
    monkeypatch, tmp_path: Path
):
    yunet, yunet_hash = model(tmp_path, "yunet.onnx", b"reviewed-yunet")
    sface, sface_hash = model(tmp_path, "sface.onnx", b"reviewed-sface")
    monkeypatch.setattr("app.services.face_service.settings.face_sface_cosine_threshold", None)
    with pytest.raises(FaceProviderUnavailable, match="threshold SFace"):
        OpenCVFaceProvider(
            cv2_module=fake_cv(),
            yunet_path=yunet,
            sface_path=sface,
            yunet_sha256=yunet_hash,
            sface_sha256=sface_hash,
        )


def test_provider_factory_selects_opencv_without_fallback(monkeypatch):
    from app.services import face_service

    expected = object()
    monkeypatch.setattr(face_service, "_get_opencv_provider", lambda *_args: expected)
    assert face_service.get_face_provider("local_opencv") is expected


def test_provider_factory_forwards_opencv_threshold_config(monkeypatch):
    from app.services import face_service

    received = []
    monkeypatch.setattr(
        face_service, "_get_opencv_provider", lambda *args: received.append(args) or object()
    )
    monkeypatch.setattr(face_service.settings, "face_yunet_confidence_threshold", 0.82)
    monkeypatch.setattr(face_service.settings, "face_yunet_nms_threshold", 0.25)
    monkeypatch.setattr(face_service.settings, "face_sface_cosine_threshold", 0.44)
    face_service.get_face_provider("local_opencv")
    assert received[0][-3:] == (0.82, 0.25, 0.44)


def test_opencv_enrollment_missing_models_fails_without_mock_fallback(monkeypatch, tmp_path: Path):
    from app.services import face_service

    image = tmp_path / "face.jpg"
    image.write_bytes(b"test-only")
    monkeypatch.setattr(face_service.settings, "face_provider", "local_opencv")
    monkeypatch.setattr(face_service.settings, "face_yunet_model_path", None)
    monkeypatch.setattr(face_service.settings, "face_sface_model_path", None)
    face_service._get_opencv_provider.cache_clear()
    with pytest.raises(FaceProviderUnavailable, match="thiếu cấu hình model YuNet"):
        FaceService().enroll_face(__import__("uuid").uuid4(), image)
    with pytest.raises(FaceProviderUnavailable, match="thiếu cấu hình model YuNet"):
        FaceService().verify_face(image, [])
    face_service._get_opencv_provider.cache_clear()
