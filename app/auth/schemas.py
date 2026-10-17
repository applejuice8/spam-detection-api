from pydantic import BaseModel, Field, model_validator


class SignupIn(BaseModel):
    username: str = Field(min_length=3, max_length=20)
    password: str = Field(min_length=8, max_length=128)
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


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = 'bearer'


class AccessTokenOut(BaseModel):
    access_token: str
    token_type: str = 'bearer'


class RefreshIn(BaseModel):
    refresh_token: str
