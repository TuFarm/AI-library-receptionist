from uuid import UUID

from datetime import UTC, datetime
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class UserRead(BaseModel):
    id: UUID
    student_code: str
    full_name: str
    email: str
    phone: str | None = None
    user_type: str
    account_status: str


class UserProfileRead(UserRead):
    faculty: str | None = None
    major: str | None = None
    admission_year: int | None = None
    calculated_student_year: int | None = None
    preferred_language: str = "vi"


class MockCurrentUserResponse(BaseModel):
    success: bool = True
    message: str = "OK"
    data: UserProfileRead


class UserProfileUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=30)
    faculty: str | None = Field(default=None, max_length=150)
    major: str | None = Field(default=None, max_length=150)
    admission_year: int | None = Field(default=None, ge=1990, le=2100)
    student_code: str | None = Field(default=None, max_length=50)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        if value and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Email không hợp lệ")
        return value or None

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, value):
        if value and not re.fullmatch(r"[+0-9() .-]{7,30}", value):
            raise ValueError("Số điện thoại không hợp lệ")
        return value or None

    @field_validator("student_code")
    @classmethod
    def valid_student_code(cls, value):
        if value and not re.fullmatch(r"[A-Za-z0-9_-]{3,50}", value):
            raise ValueError("Mã sinh viên không hợp lệ")
        return value or None

    @model_validator(mode="after")
    def at_least_one_field(self):
        if not self.model_fields_set:
            raise ValueError("Cần ít nhất một trường để cập nhật")
        if "full_name" in self.model_fields_set and self.full_name is None:
            raise ValueError("Họ và tên không được để trống")
        if self.admission_year is not None and self.admission_year > datetime.now(UTC).year + 1:
            raise ValueError("Năm nhập học không hợp lệ")
        return self
