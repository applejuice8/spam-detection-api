from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.auth.models import User, RefreshToken, APIKey
from app.core.security import hash_password, verify_password, fast_hash, DUMMY_HASH
from app.auth.schemas import SignupIn, LoginIn
from datetime import datetime, timezone, timedelta
from app.core.config import get_settings
import secrets


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
        raise ValueError('Username already exists') from None
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
        token=fast_hash(raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=get_settings().refresh_token_expire_days)
    )
    db.add(refresh_token)
    await db.commit()


async def consume_refresh_token(db: AsyncSession, raw_token: str) -> int | None:
    result = await db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token == fast_hash(raw_token),
            RefreshToken.revoked.is_(False),
            RefreshToken.expires_at > datetime.now(timezone.utc)
        )
        .values(revoked=True)
        .returning(RefreshToken.user_id)
    )
    user_id = result.scalar_one_or_none()
    await db.commit()
    return user_id


# API Key
async def create_api_key(db: AsyncSession, user_id: int, expires_in_days: int) -> tuple[APIKey, str]:
    raw_key = 'sk_' + secrets.token_urlsafe(32)
    api_key = APIKey(
        user_id=user_id,
        prefix=raw_key[:9],
        key_hash=fast_hash(raw_key),
        expires_at=datetime.now(timezone.utc) + timedelta(days=expires_in_days)
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    return api_key, raw_key


async def list_api_keys(db: AsyncSession, user_id: int) -> list[APIKey]:
    api_keys = await db.scalars(
        select(APIKey)
        .where(APIKey.user_id == user_id)
        .order_by(APIKey.created_at.desc())
    )
    return list(api_keys)


async def revoke_api_key(db: AsyncSession, user_id: int, key_id: int) -> bool:
    result = await db.execute(
        update(APIKey)
        .where(APIKey.id == key_id, APIKey.user_id == user_id, APIKey.revoked.is_(False))
        .values(revoked=True)
        .returning(APIKey.id)
    )
    api_key_id = result.scalar_one_or_none()
    await db.commit()
    return api_key_id is not None
