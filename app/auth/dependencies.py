from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from typing import Annotated
from app.db import DBDep
from app.core.security import decode_access_token
from app.auth.models import User


oauth2_scheme = OAuth2PasswordBearer(tokenUrl='/auth/login')

OAuth2Dep = Annotated[str, Depends(oauth2_scheme)]


async def get_current_user(token: OAuth2Dep, db: DBDep) -> User:
    try:
        payload = decode_access_token(token)
        user_id = int(payload['sub'])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            'Token expired',
            headers={'WWW-Authenticate': 'Bearer'}
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            'Invalid token',
            headers={'WWW-Authenticate': 'Bearer'}
        )

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            'User not found',
            headers={'WWW-Authenticate': 'Bearer'}
        )
    return user


UserDep = Annotated[User, Depends(get_current_user)]
