class PresenceDetector:
    def __init__(self, confirmation_seconds: float = 1.2):
        self.confirmation_seconds = confirmation_seconds
        self.present_since: float | None = None

    def update(self, visible: bool, now: float) -> tuple[bool, bool]:
        if not visible:
            was_present = self.present_since is not None
            self.present_since = None
            return False, was_present
        self.present_since = self.present_since or now
        return now - self.present_since >= self.confirmation_seconds, False

    def reset(self):
        self.present_since = None
