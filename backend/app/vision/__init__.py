"""Realtime vision primitives. They are connection-scoped and contain no UI or database state."""

from app.vision.engine import VisionEngine
from app.vision.face_tracker import FaceTracker, Track, overlap
from app.vision.identity_voting import IdentityVoting

__all__ = ["VisionEngine", "FaceTracker", "Track", "IdentityVoting", "overlap"]
