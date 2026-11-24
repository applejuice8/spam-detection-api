from app.db import Base
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, DateTime, func, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import CITEXT
from datetime import datetime


class User(Base):
    __tablename__ = 'user'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(
        CITEXT().with_variant(String(20, collation='NOCASE'), 'sqlite'),    # Use String for sqlite
        unique=True,
        nullable=False,
    )
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    tokens_valid_after: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class RefreshToken(Base):
    __tablename__ = 'refresh_token'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey('user.id', ondelete='CASCADE'),
        index=True
    )
    token: Mapped[str] = mapped_column(String(255), unique=True)
    family_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class APIKey(Base):
    __tablename__ = 'api_key'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey('user.id', ondelete='CASCADE'),
        index=True
    )
    prefix: Mapped[str] = mapped_column(String(9))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
