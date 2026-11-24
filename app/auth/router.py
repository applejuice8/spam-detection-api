from fastapi import APIRouter, status, HTTPException, Depends
from typing import Annotated
from app.db import DBDep
from app.auth.dependencies import UserDep
from app.auth.schemas import SignupIn, LoginIn, UserOut, TokenOut, RefreshIn, APIKeyCreateIn, APIKeyCreatedOut, APIKeyOut
from app.auth.service import (
    create_user, authenticate_user, store_refresh_token, rotate_refresh_token, revoke_refresh_family,
    revoke_all_sessions, create_api_key, list_api_keys, revoke_api_key
)
from app.core.security import create_access_token, create_refresh_token
from app.core import rate_limit
from fastapi.security import OAuth2PasswordRequestForm


router = APIRouter(prefix='/auth', tags=['auth'])


@router.post(
    '/signup', response_model=UserOut, status_code=status.HTTP_201_CREATED,
    dependencies=[rate_limit.limit_by_ip('signup')]
)
async def signup(req: SignupIn, db: DBDep):
    try:
        return await create_user(db, req)
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None


@router.post('/login', response_model=TokenOut, dependencies=[rate_limit.limit_by_ip('login')])
async def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DBDep):
    user = await authenticate_user(db, LoginIn(username=form.username, password=form.password))
    if not user:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            'Incorrect username or password',
            headers={'WWW-Authenticate': 'Bearer'}
        )

    access = create_access_token(user.id)
    refresh = create_refresh_token()
    await store_refresh_token(db, user.id, refresh)

    return TokenOut(access_token=access, refresh_token=refresh)


@router.post('/refresh', response_model=TokenOut, dependencies=[rate_limit.limit_by_ip('refresh')])
async def refresh(req: RefreshIn, db: DBDep):
    # Refresh token only works once
    new_refresh = create_refresh_token()
    user_id = await rotate_refresh_token(db, req.refresh_token, new_refresh)
    if user_id is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            'Invalid or expired refresh token',
            headers={'WWW-Authenticate': 'Bearer'}
        )

    return TokenOut(access_token=create_access_token(user_id), refresh_token=new_refresh)


@router.post('/logout', status_code=status.HTTP_204_NO_CONTENT)
async def logout(req: RefreshIn, db: DBDep):
    await revoke_refresh_family(db, req.refresh_token)


# Revokes every refresh token. Access tokens issued before now stop working too.
@router.post('/logout-all', status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(user: UserDep, db: DBDep):
    await revoke_all_sessions(db, user.id)


# API keys
@router.post('/api-keys', response_model=APIKeyCreatedOut, status_code=status.HTTP_201_CREATED)
async def create_key(req: APIKeyCreateIn, user: UserDep, db: DBDep):
    api_key, raw_key = await create_api_key(db, user.id, req.expires_in_days)
    return APIKeyCreatedOut(
        id=api_key.id,
        prefix=api_key.prefix,
        created_at=api_key.created_at,
        expires_at=api_key.expires_at,
        revoked=api_key.revoked,
        api_key=raw_key
    )


@router.get('/api-keys', response_model=list[APIKeyOut])
async def list_keys(user: UserDep, db: DBDep):
    return await list_api_keys(db, user.id)


@router.delete('/api-keys/{key_id}', status_code=status.HTTP_204_NO_CONTENT)
async def revoke_key(key_id: int, user: UserDep, db: DBDep):
    if not await revoke_api_key(db, user.id, key_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'API key not found')


# Protected route
@router.get('/me', response_model=UserOut)
async def me(user: UserDep):
    return user
