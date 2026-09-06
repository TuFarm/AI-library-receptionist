from dataclasses import dataclass


@dataclass
class SessionController:
    mode: str = "idle"
    session_id: str | None = None
    locked: bool = False
    proposal: object | None = None

    def configure(self, mode: str, session_id: str | None):
        if mode not in {"idle", "recognition", "registration", "conversation"}:
            raise ValueError("Invalid sensor mode")
        self.mode = mode
        self.session_id = session_id
        self.locked = mode == "conversation"
        self.proposal = None

    def offer(self, result):
        self.proposal = result
        self.locked = True

    def accept(self, session_id):
        if self.mode != "recognition" or session_id != self.session_id or self.proposal is None:
            return None
        result = self.proposal
        self.proposal = None
        return result
