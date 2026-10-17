from pwdlib import PasswordHash
import jwt
from app.core.config import get_settings
from datetime import datetime, timezone, timedelta
import secrets
from hashlib import sha256


settings = get_settings()
ph = PasswordHash.recommended()


# Always hash password even if user doesnt exist
# Hackers can check response time to see which username exists
# Dummy hash used to equalize timing when a username doesn't exist
DUMMY_HASH = ph.hash('you-are-stupid')


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return ph.verify(password, hashed)


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        'sub': str(user_id),
        'iat': now,
        'exp': now + timedelta(minutes=settings.access_token_expires_minutes),
        'type': 'access'
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={'require': ['exp', 'sub']}
    )
    if payload.get('type') != 'access':
        raise jwt.InvalidTokenError('Wrong token type')
    return payload


# Opaque random string, NOT a JWT
def create_refresh_token() -> str:
    return secrets.token_urlsafe(48)


# Already random, don't need long salted hash
# String -> Bytes -> Hex string
def hash_refresh_token(raw_token: str) -> str:
    return sha256(raw_token.encode()).hexdigest()
