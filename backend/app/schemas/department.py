"""Pydantic schemas for department and major management."""
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from uuid import UUID


class DepartmentCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    code: str = Field(min_length=2, max_length=20)
    name: str = Field(min_length=2, max_length=255)

    @field_validator("code")
    @classmethod
    def valid_code(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]{2,20}", value):
            raise ValueError("Mã khoa chỉ chứa chữ cái, số, gạch ngang, gạch dưới")
        return value.upper()


class DepartmentUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str | None = Field(default=None, min_length=2, max_length=255)
    is_active: bool | None = Field(default=None, strict=True)

    @model_validator(mode="after")
    def valid_changes(self):
        if not self.model_fields_set or any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("Cần ít nhất một trường và giá trị không được null")
        return self


class DepartmentRead(BaseModel):
    id: UUID
    code: str
    name: str
    is_active: bool


class MajorCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    department_id: UUID
    code: str = Field(min_length=2, max_length=30)
    name: str = Field(min_length=2, max_length=255)

    @field_validator("code")
    @classmethod
    def valid_code(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]{2,30}", value):
            raise ValueError("Mã ngành chỉ chứa chữ cái, số, gạch ngang, gạch dưới")
        return value.upper()


class MajorUpdate(DepartmentUpdate):
    pass


class MajorRead(BaseModel):
    id: UUID
    department_id: UUID
    code: str
    name: str
    is_active: bool
