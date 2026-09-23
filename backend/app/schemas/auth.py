"""Authentication and authorization schemas."""
from pydantic import BaseModel, Field


class TokenPayload(BaseModel):
    sub: str  # user ID
    role: str  # 'admin' or 'librarian'
    exp: int


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=6, max_length=200)


class RefreshRequest(BaseModel):
    refresh_token: str
