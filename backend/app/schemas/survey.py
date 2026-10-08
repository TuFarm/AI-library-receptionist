from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID

# Question types the kiosk survey screen can render.
QuestionType = Literal["rating", "yes_no", "text"]
YES_NO_CHOICES = ("Có", "Không")
MAX_TEXT_ANSWER = 1000


class SurveySubmission(BaseModel):
    answers: dict[str, Any] = Field(min_length=1)
    session_id: UUID | None = None
    user_id: UUID | None = None


class SurveyQuestionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question_text: str = Field(min_length=3, max_length=500)
    question_type: QuestionType


class SurveyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    survey_name: str = Field(min_length=3, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    questions: list[SurveyQuestionInput] = Field(min_length=1, max_length=20)


class SurveyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    survey_name: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    questions: list[SurveyQuestionInput] | None = Field(default=None, min_length=1, max_length=20)
