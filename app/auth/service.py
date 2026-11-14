from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.auth.models import User, RefreshToken, APIKey
from app.core.security import as_utc, hash_password, verify_password, fast_hash, DUMMY_HASH
from app.auth.schemas import PASSWORD_MAX_LENGTH, SignupIn, LoginIn
from datetime import datetime, timezone, timedelta
from app.core.config import get_settings
import secrets
import uuid


async def create_user(db: AsyncSession, data: SignupIn) -> User:
    existing = await db.scalar(select(User).where(func.lower(User.username) == data.username.lower()))
    if existing:
        raise ValueError('Username already exists')

    # Argon2 is deliberately slow CPU work. In a thread, it can't stall other requests.
    user = User(username=data.username, password=await run_in_threadpool(hash_password, data.password))
    db.add(user)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ValueError('Username already exists') from None
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, data: LoginIn) -> User | None:
    # No account can have a longer password (signup caps it), so skip the expensive hash
    if len(data.password) > PASSWORD_MAX_LENGTH:
        return None

    user = await db.scalar(select(User).where(func.lower(User.username) == data.username.lower()))

    # Fake hash time if no such user
    if not user:
        await run_in_threadpool(verify_password, data.password, DUMMY_HASH)
        return None

    if not await run_in_threadpool(verify_password, data.password, user.password):
        return None
    return user


def _new_refresh_row(user_id: int, raw_token: str, family_id: str) -> RefreshToken:
    return RefreshToken(
        user_id=user_id,
        token=fast_hash(raw_token),
        family_id=family_id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=get_settings().refresh_token_expire_days)
    )


# Login: start a new family
async def store_refresh_token(db: AsyncSession, user_id: int, raw_token: str) -> None:
    db.add(_new_refresh_row(user_id, raw_token, str(uuid.uuid4())))
    await db.commit()


async def _revoke_family(db: AsyncSession, row: RefreshToken) -> None:
    if row.family_id is None:
        stmt = update(RefreshToken).where(RefreshToken.id == row.id)
    else:
        stmt = update(RefreshToken).where(RefreshToken.family_id == row.family_id)
    await db.execute(stmt.values(revoked=True).execution_options(synchronize_session=False))


# Swap a refresh token for a new one in a single transaction, so a failure can't leave the user logged out.
# Presenting a token that was already used means it was probably stolen, so its whole family is revoked.
async def rotate_refresh_token(db: AsyncSession, raw_token: str, new_raw_token: str) -> int | None:
    row = await db.scalar(select(RefreshToken).where(RefreshToken.token == fast_hash(raw_token)))
    if row is None:
        return None

    if row.revoked:
        await _revoke_family(db, row)
        await db.commit()
        return None

    # The conditional update is what makes this safe when two requests present the same token at once
    claimed = await db.scalar(
        update(RefreshToken)
        .where(
            RefreshToken.id == row.id,
            RefreshToken.revoked.is_(False),
            RefreshToken.expires_at > datetime.now(timezone.utc)
        )
        .values(revoked=True)
        .returning(RefreshToken.id)
        # Skip re-checking the WHERE clause against loaded objects in Python. The database is the source of truth.
        .execution_options(synchronize_session=False)
    )
    if claimed is None:
        # Expired, or lost a race against another use of the same token
        if as_utc(row.expires_at) > datetime.now(timezone.utc):
            await _revoke_family(db, row)
        await db.commit()
        return None

    db.add(_new_refresh_row(row.user_id, new_raw_token, row.family_id or str(uuid.uuid4())))
    await db.commit()
    return row.user_id


# Logout: end this login on this device, including any newer tokens from refreshing it
async def revoke_refresh_family(db: AsyncSession, raw_token: str) -> None:
    row = await db.scalar(select(RefreshToken).where(RefreshToken.token == fast_hash(raw_token)))
    if row is not None:
        await _revoke_family(db, row)
        await db.commit()


# Log out everywhere: revoke every refresh token and invalidate access tokens issued so far
async def revoke_all_sessions(db: AsyncSession, user_id: int) -> None:
    await db.execute(update(RefreshToken).where(RefreshToken.user_id == user_id).values(revoked=True))
    await db.execute(update(User).where(User.id == user_id).values(tokens_valid_after=datetime.now(timezone.utc)))
    await db.commit()


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
