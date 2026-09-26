from app.db import Base
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, DateTime, func

class User(Base):
    __tablename__ = 'user'

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True
    )
    username: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False
    )
    password: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime,
        server_default=func.now()
    )
