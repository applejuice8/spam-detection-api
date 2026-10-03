from pydantic import BaseModel, Field


class SignupIn(BaseModel):
    username: str
    password: str = Field(min_length=8)
    confirm_password: str = Field(min_length=8)


class LoginIn(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = 'bearer'


class AccessTokenOut(BaseModel):
    access_token: str
    token_type: str = 'bearer'


class RefreshIn(BaseModel):
    refresh_token: str
