from fastapi import APIRouter, status, HTTPException
from app.dependencies import DBDep
from app.auth.dependencies import UserDep
from app.auth.schemas import SignupIn, LoginIn, UserOut, TokenOut, AccessTokenOut, RefreshIn
from app.auth.models import User
from app.auth.service import create_user, authenticate_user, store_refresh_token, verify_refresh_token, revoke_refresh_token
from app.core.security import create_access_token, create_refresh_token


router = APIRouter(prefix='/auth', tags=['auth'])


@router.post('/signup', response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def signup(req: SignupIn, db: DBDep):
    try:
        return await create_user(db, req)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@router.post('/login', response_model=TokenOut)
async def login(req: LoginIn, db: DBDep):
    user = await authenticate_user(db, req.username, req.password)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, 'Incorrect username or password')

    access = create_access_token(user.id)
    refresh = create_refresh_token()
    await store_refresh_token(db, user.id, refresh)

    return TokenOut(access_token=access, refresh_token=refresh)


@router.post('/refresh', response_model=AccessTokenOut)
async def refresh(req: RefreshIn, db: DBDep):
    user_id = await verify_refresh_token(db, req.refresh_token)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, 'Invalid or expired refresh token')
    return AccessTokenOut(access_token=create_access_token(user_id))



@router.post('/logout', status_code=status.HTTP_204_NO_CONTENT)
async def logout(req: RefreshIn, db: DBDep):
    await revoke_refresh_token(db, req.refresh_token)


@router.get('/me', response_model=UserOut)
async def readme(user: UserDep):
    return user
