from fastapi import Depends, HTTPException, status, Security
from fastapi.security import OAuth2PasswordBearer, APIKeyHeader
import jwt
from typing import Annotated
from app.db import DBDep
from app.core.security import as_utc, decode_access_token, fast_hash
from app.auth.models import User, APIKey
from app.core.metrics import API_KEY_REJECTIONS
from sqlalchemy import select
from datetime import datetime, timezone


# OAuth2
oauth2_scheme = OAuth2PasswordBearer(tokenUrl='/auth/login')
OAuth2Dep = Annotated[str, Depends(oauth2_scheme)]


# User
async def get_current_user(token: OAuth2Dep, db: DBDep) -> User:
    try:
        payload = decode_access_token(token)
        user_id = int(payload['sub'])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            'Token expired',
            headers={'WWW-Authenticate': 'Bearer'}
        ) from None
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            'Invalid token',
            headers={'WWW-Authenticate': 'Bearer'}
        ) from None

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            'User not found',
            headers={'WWW-Authenticate': 'Bearer'}
        )

    # "Log out everywhere" invalidates access tokens issued at or before that moment.
    # iat has one-second precision, so a token issued in the same second counts as before.
    if user.tokens_valid_after and payload['iat'] <= int(as_utc(user.tokens_valid_after).timestamp()):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            'Token revoked',
            headers={'WWW-Authenticate': 'Bearer'}
        )
    return user


UserDep = Annotated[User, Depends(get_current_user)]


# API Key
api_key_header = APIKeyHeader(name='X-API-Key', auto_error=False)
APIKeyDep = Annotated[str | None, Security(api_key_header)]


async def get_api_key_user(api_key: APIKeyDep, db: DBDep) -> User:
    if not api_key:
        API_KEY_REJECTIONS.labels(reason='missing').inc()
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            'Missing API Key',
            headers={'WWW-Authenticate': 'APIKey'}
        )

    user = await db.scalar(
        select(User)
        .join(APIKey, APIKey.user_id == User.id)
        .where(
            APIKey.key_hash == fast_hash(api_key),
            APIKey.revoked.is_(False),
            APIKey.expires_at > datetime.now(timezone.utc)
        )
    )
    if not user:
        API_KEY_REJECTIONS.labels(reason='invalid').inc()
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            'Invalid or expired API key',
            headers={'WWW-Authenticate': 'APIKey'}
        )
    return user


APIKeyUserDep = Annotated[User, Depends(get_api_key_user)]
