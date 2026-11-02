from fastapi import APIRouter, status, HTTPException, Depends
from typing import Annotated
from app.db import DBDep
from app.auth.dependencies import UserDep
from app.auth.schemas import SignupIn, LoginIn, UserOut, TokenOut, RefreshIn, APIKeyCreatedOut, APIKeyOut
from app.auth.service import create_user, authenticate_user, store_refresh_token, consume_refresh_token, create_api_key, list_api_keys, revoke_api_key
from app.core.security import create_access_token, create_refresh_token
from fastapi.security import OAuth2PasswordRequestForm


router = APIRouter(prefix='/auth', tags=['auth'])


@router.post('/signup', response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def signup(req: SignupIn, db: DBDep):
    try:
        return await create_user(db, req)
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))


@router.post('/login', response_model=TokenOut)
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


@router.post('/refresh', response_model=TokenOut)
async def refresh(req: RefreshIn, db: DBDep):
    user_id = await consume_refresh_token(db, req.refresh_token)
    if user_id is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            'Invalid or expired refresh token',
            headers={'WWW-Authenticate': 'Bearer'}
        )

    # Refresh token only works once
    new_refresh = create_refresh_token()
    await store_refresh_token(db, user_id, new_refresh)
    return TokenOut(access_token=create_access_token(user_id), refresh_token=new_refresh)


@router.post('/logout', status_code=status.HTTP_204_NO_CONTENT)
async def logout(req: RefreshIn, db: DBDep):
    await consume_refresh_token(db, req.refresh_token)


# API keys
@router.post('/api-keys', response_model=APIKeyCreatedOut, status_code=status.HTTP_201_CREATED)
async def create_key(user: UserDep, db: DBDep):
    api_key, raw_key = await create_api_key(db, user.id)
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
