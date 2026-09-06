from dataclasses import dataclass, field
from math import hypot

from app.vision.identity_voting import IdentityVoting


def overlap(a, b):
    top, right, bottom, left = a
    other_top, other_right, other_bottom, other_left = b
    intersection = max(0, min(right, other_right) - max(left, other_left)) * max(
        0, min(bottom, other_bottom) - max(top, other_top)
    )
    union = (right - left) * (bottom - top) + (other_right - other_left) * (
        other_bottom - other_top
    ) - intersection
    return intersection / union if union else 0


@dataclass
class Track:
    id: int
    box: tuple[int, int, int, int]
    seen: float
    stable_since: float
    last_recognition: float = 0
    hits: int = 1
    missed_frames: int = 0
    last_iou: float = 1.0
    created: float | None = None
    voting: IdentityVoting = field(default_factory=IdentityVoting)

    def __post_init__(self):
        if self.created is None:
            self.created = self.seen

    @property
    def candidate(self):
        return self.voting.candidate

    @property
    def votes(self):
        return self.voting.votes

    def reset(self):
        self.voting.reset()

    def vote(self, candidate):
        return self.voting.observe(candidate)


class FaceTracker:
    def __init__(self, max_missed_frames: int = 5):
        self.tracks: dict[int, Track] = {}
        self.next_id = 1
        self.max_missed_frames = max_missed_frames
        self.last_events: list[dict] = []
        self.created_count = 0
        self.updated_count = 0
        self.lost_count = 0
        self.lost_lifetimes_ms: list[float] = []

    @staticmethod
    def _compatible(previous, current):
        previous_top, previous_right, previous_bottom, previous_left = previous
        top, right, bottom, left = current
        previous_width = max(1, previous_right - previous_left)
        previous_height = max(1, previous_bottom - previous_top)
        width = max(1, right - left)
        height = max(1, bottom - top)
        center_distance = hypot(
            (left + right - previous_left - previous_right) / 2,
            (top + bottom - previous_top - previous_bottom) / 2,
        )
        scale = max(hypot(previous_width, previous_height), hypot(width, height))
        size_ratio = min(width * height, previous_width * previous_height) / max(
            width * height, previous_width * previous_height
        )
        return overlap(previous, current) >= .25 or (center_distance / scale <= .35 and size_ratio >= .5)

    def update(self, boxes, now):
        self.last_events = []
        available = set(self.tracks)
        visible = []
        for box in boxes:
            compatible = [key for key in available if self._compatible(self.tracks[key].box, box)]
            best = max(compatible, key=lambda key: overlap(self.tracks[key].box, box), default=None)
            if best is None:
                track = Track(self.next_id, box, now, now)
                self.next_id += 1
                self.tracks[track.id] = track
                self.created_count += 1
                self.last_events.append({"event": "track_created", "track_id": track.id})
            else:
                available.remove(best)
                track = self.tracks[best]
                track.last_iou = overlap(track.box, box)
                if track.last_iou < .55:
                    track.stable_since = now
                    track.reset()
                track.box, track.seen = box, now
                track.hits += 1
                track.missed_frames = 0
                self.updated_count += 1
                self.last_events.append({"event": "track_updated", "track_id": track.id})
            visible.append(track)
        for key in available:
            track = self.tracks[key]
            track.missed_frames += 1
            track.reset()
            track.stable_since = now
            if track.missed_frames > self.max_missed_frames:
                lifetime_ms = round((now - track.created) * 1000, 1)
                self.lost_count += 1
                self.lost_lifetimes_ms.append(lifetime_ms)
                self.last_events.append({"event": "track_lost", "track_id": track.id,
                                         "hits": track.hits, "lost_after_ms": lifetime_ms})
                del self.tracks[key]
        return visible

    @property
    def metrics(self):
        observations = self.created_count + self.updated_count
        return {
            "active_tracks": len(self.tracks),
            "tracks_created": self.created_count,
            "tracks_updated": self.updated_count,
            "tracks_lost": self.lost_count,
            "track_recreation_rate": round(self.created_count / observations, 4) if observations else 0,
            "track_lost_rate": round(self.lost_count / self.created_count, 4) if self.created_count else 0,
            "mean_lost_lifetime_ms": round(sum(self.lost_lifetimes_ms) / len(self.lost_lifetimes_ms), 1)
            if self.lost_lifetimes_ms else None,
        }
