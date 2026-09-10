from io import BytesIO
from typing import Any

from app.services.face_service import InvalidFaceImageError


class InvalidImageError(InvalidFaceImageError):
    pass


class ImageDecoder:
    """Decode transport bytes only; face providers receive an RGB image array."""

    def decode(self, data: bytes) -> Any:
        try:
            import numpy as np
            from PIL import Image, UnidentifiedImageError

            with Image.open(BytesIO(data)) as source:
                if source.width > 1920 or source.height > 1080:
                    raise InvalidImageError("Frame dimensions exceed 1920×1080")
                return np.asarray(source.convert("RGB"))
        except InvalidImageError:
            raise
        except (OSError, ValueError, UnidentifiedImageError) as exc:
            raise InvalidImageError("Invalid image data") from exc
