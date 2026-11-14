from pydantic import BaseModel, Field, model_validator, ConfigDict
from datetime import datetime
from typing import Literal


PASSWORD_MAX_LENGTH = 128


class SignupIn(BaseModel):
    username: str = Field(min_length=3, max_length=20)
    password: str = Field(min_length=8, max_length=PASSWORD_MAX_LENGTH)
    confirm_password: str

    @model_validator(mode='after')
    def passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError('Passwords do not match')
        return self

class LoginIn(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str


# JWT Token
class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = 'bearer'


class RefreshIn(BaseModel):
    refresh_token: str


# API Key
# Lifetime choices for a new key. Free-form values are rejected.
class APIKeyCreateIn(BaseModel):
    expires_in_days: Literal[7, 30, 90, 180, 365] = 90


class APIKeyOut(BaseModel):
    id: int
    prefix: str
    created_at: datetime
    expires_at: datetime
    revoked: bool

    model_config = ConfigDict(from_attributes=True)


class APIKeyCreatedOut(APIKeyOut):
    # Raw key, only returned once at creation
    api_key: str
