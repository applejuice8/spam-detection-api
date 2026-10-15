from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.models import User, RefreshToken
from app.core.security import hash_password, verify_password, DUMMY_HASH
from app.auth.schemas import SignupIn, LoginIn
from datetime import datetime, timezone
from app.core.config import get_settings


async def create_user(db: AsyncSession, data: SignupIn) -> User:
    existing = await db.scalar(select(User).where(User.username == data.username))
    if existing:
        raise ValueError('Username already exists')

    hashed = hash_password(data.password)
    user = User(username=data.username, password=hashed)
    db.add(user)
    await db.commit()
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
    hashed = hash_password(raw_token)
    refresh_token = RefreshToken(
        user_id=user_id,
        token=hashed,
        expires_at=datetime.now(timezone.utc) + get_settings().refresh_token_expire_days
    )
    db.add(refresh_token)
    await db.refresh()


async def verify_refresh_token(db: AsyncSession, raw_token: str) -> int | None:
    tokens = await db.scalars(
        select(RefreshToken).where(
            RefreshToken.revoked == False,
            RefreshToken.expires_at > datetime.now(timezone.utc)
        )
    )
    for token in tokens:
        if verify_password(raw_token, token.token):
            return token.user_id
    return None


async def revoke_refresh_token(db: AsyncSession, raw_token: str) -> None:
    user_id = await verify_refresh_token(db, raw_token)
    if user_id is None:
        return

    stmt = (
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked == False)
        .values(revoked=True)
    )
    await db.execute(stmt)
    await db.commit()

