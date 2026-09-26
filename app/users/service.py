from sqlalchemy.ext.asyncio import AsyncSession
from app.users.models import User
from app.dependencies import ph

def create_user(username: str, password: str, db: AsyncSession) -> User:
    user = User(username=username, password=ph.hash(password))
    db.add(user)
    db.commit()
    return user

