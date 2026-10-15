from app.core.config import get_settings
from app.db import get_db
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

DBDep = Annotated[AsyncSession, Depends(get_db)]

__all__ = ['get_settings', 'DBDep']
