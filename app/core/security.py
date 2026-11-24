from pwdlib import PasswordHash
import jwt
from app.core.config import get_settings
from datetime import datetime, timezone, timedelta
import secrets
from hashlib import sha256


# Fixed on purpose: a configurable algorithm invites downgrade and misconfiguration
JWT_ALGORITHM = 'HS256'

settings = get_settings()
ph = PasswordHash.recommended()


# Always hash password even if user doesnt exist
# Hackers can check response time to see which username exists
# Dummy hash used to equalize timing when a username doesn't exist
DUMMY_HASH = ph.hash('you-are-stupid')


# Store times in UTC (SQLite returns naive datetimes, Postgres returns aware ones)
def as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


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
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[JWT_ALGORITHM],
        options={'require': ['exp', 'sub', 'iat']}
    )
    if payload.get('type') != 'access':
        raise jwt.InvalidTokenError('Wrong token type')
    return payload


# Opaque random string, NOT a JWT
def create_refresh_token() -> str:
    return secrets.token_urlsafe(48)


# Already random, don't need long salted hash
# String -> Bytes -> Hex string
def fast_hash(raw: str) -> str:
    return sha256(raw.encode()).hexdigest()
