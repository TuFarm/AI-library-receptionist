from dataclasses import dataclass


@dataclass
class IdentityVoting:
    required_votes: int = 3
    candidate: str | None = None
    votes: int = 0

    def reset(self) -> None:
        self.candidate = None
        self.votes = 0

    def observe(self, candidate: str | None) -> bool:
        if not candidate:
            self.reset()
            return False
        self.votes = self.votes + 1 if candidate == self.candidate else 1
        self.candidate = candidate
        return self.votes >= self.required_votes
