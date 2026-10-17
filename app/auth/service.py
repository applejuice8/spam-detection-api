from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.auth.models import User, RefreshToken
from app.core.security import hash_password, verify_password, hash_refresh_token, DUMMY_HASH
from app.auth.schemas import SignupIn, LoginIn
from datetime import datetime, timezone, timedelta
from app.core.config import get_settings


async def create_user(db: AsyncSession, data: SignupIn) -> User:
    existing = await db.scalar(select(User).where(User.username == data.username))
    if existing:
        raise ValueError('Username already exists')

    user = User(username=data.username, password=hash_password(data.password))
    db.add(user)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ValueError('Username already exists')
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, data: LoginIn) -> User | None:
    user = await db.scalar(select(User).where(User.username == data.username))

    # Fake hash time if no such user
    if not user:
        verify_password(data.password, DUMMY_HASH)
        return None

    if not verify_password(data.password, user.password):
        return None
    return user


async def store_refresh_token(db: AsyncSession, user_id: int, raw_token: str) -> None:
    refresh_token = RefreshToken(
        user_id=user_id,
        token=hash_refresh_token(raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=get_settings().refresh_token_expire_days)
    )
    db.add(refresh_token)
    await db.commit()


async def consume_refresh_token(db: AsyncSession, raw_token: str) -> int | None:
    result = await db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token == hash_refresh_token(raw_token),
            RefreshToken.revoked == False,
            RefreshToken.expires_at > datetime.now(timezone.utc)
        )
        .values(revoked=True)
        .returning(RefreshToken.user_id)
    )
    user_id = result.scalar_one_or_none()
    await db.commit()
    return user_id
