"""Staff authentication, staff account and kiosk device schemas."""
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

StaffRole = Literal["admin", "librarian"]
USERNAME_PATTERN = re.compile(r"^[a-z0-9._-]{3,100}$")
DEVICE_CODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{2,80}$")


def _password(value: str) -> str:
    if not value.strip():
        raise ValueError("Mật khẩu không được chỉ gồm khoảng trắng.")
    return value


class AdminLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


class AdminPasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=8, max_length=128)

    _check_new = field_validator("new_password")(_password)


class StaffCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=100)
    full_name: str = Field(min_length=1, max_length=255)
    role: StaffRole = "librarian"
    password: str = Field(min_length=8, max_length=128)

    _check_password = field_validator("password")(_password)

    @field_validator("username")
    @classmethod
    def valid_username(cls, value: str) -> str:
        value = value.strip().lower()
        if not USERNAME_PATTERN.fullmatch(value):
            raise ValueError("Tên đăng nhập chỉ gồm chữ thường, số, dấu chấm, gạch dưới hoặc gạch ngang.")
        return value

    @field_validator("full_name")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Họ tên không được để trống.")
        return value.strip()


class StaffUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    role: StaffRole | None = None
    is_active: bool | None = None

    @field_validator("full_name")
    @classmethod
    def not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Họ tên không được để trống.")
        return value


class StaffPasswordReset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    new_password: str = Field(min_length=8, max_length=128)

    _check_new = field_validator("new_password")(_password)


class DeviceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_code: str = Field(min_length=2, max_length=80)
    device_name: str = Field(min_length=1, max_length=150)
    location: str | None = Field(default=None, max_length=255)

    @field_validator("device_code")
    @classmethod
    def valid_code(cls, value: str) -> str:
        value = value.strip().upper()
        if not DEVICE_CODE_PATTERN.fullmatch(value):
            raise ValueError("Mã thiết bị chỉ gồm chữ, số, gạch dưới hoặc gạch ngang.")
        return value


class DeviceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_name: str | None = Field(default=None, min_length=1, max_length=150)
    location: str | None = Field(default=None, max_length=255)
    status: Literal["active", "disabled"] | None = None
