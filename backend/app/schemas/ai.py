from pydantic import BaseModel, Field
from uuid import UUID


class AIRuntimeRequest(BaseModel):
    conversation_id: UUID
    session_id: UUID | None = None
    message_text: str = Field(min_length=1, max_length=4000)
    # Browser voice transcripts are already persisted by /voice/browser-transcript.
    save_user_message: bool = True
