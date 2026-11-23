"""unique username ignoring case

Revision ID: c3a1d5e7b902
Revises: b967dc076701
Create Date: 2026-11-14 17:00:00.000000

Fails if two existing users differ only by case. Rename one of them first, then rerun.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c3a1d5e7b902'
down_revision: Union[str, Sequence[str], None] = 'b967dc076701'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute('CREATE EXTENSION IF NOT EXISTS citext')
    op.alter_column(
        'user',
        'username',
        existing_type=sa.String(length=20),
        type_=postgresql.CITEXT(),
        existing_nullable=False,
    )
    op.drop_index('ix_user_username_lower', table_name='user')


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        'user',
        'username',
        existing_type=postgresql.CITEXT(),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
    op.create_index('ix_user_username_lower', 'user', [sa.text('lower(username)')], unique=True)
