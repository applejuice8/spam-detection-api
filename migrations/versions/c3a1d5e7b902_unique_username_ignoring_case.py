"""unique username ignoring case

Revision ID: c3a1d5e7b902
Revises: b967dc076701
Create Date: 2026-11-14 17:00:00.000000

Fails if two existing users differ only by case. Rename one of them first, then rerun.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3a1d5e7b902'
down_revision: Union[str, Sequence[str], None] = 'b967dc076701'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index('ix_user_username_lower', 'user', [sa.text('lower(username)')], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_user_username_lower', table_name='user')
