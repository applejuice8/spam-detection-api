"""refresh token family and session cutoff

Revision ID: d4b2e6f8a013
Revises: c3a1d5e7b902
Create Date: 2026-11-14 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4b2e6f8a013'
down_revision: Union[str, Sequence[str], None] = 'c3a1d5e7b902'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Existing refresh-token rows predate family tracking. Give each old token its
    # own family before enforcing NOT NULL; the id makes these values unique.
    op.add_column('refresh_token', sa.Column('family_id', sa.String(length=36), nullable=True))
    refresh_token = sa.table(
        'refresh_token',
        sa.column('id', sa.Integer()),
        sa.column('family_id', sa.String(length=36)),
    )
    op.get_bind().execute(
        refresh_token.update()
        .where(refresh_token.c.family_id.is_(None))
        .values(family_id=sa.literal('legacy-') + sa.cast(refresh_token.c.id, sa.String()))
    )
    op.alter_column(
        'refresh_token',
        'family_id',
        existing_type=sa.String(length=36),
        nullable=False,
    )
    op.create_index(op.f('ix_refresh_token_family_id'), 'refresh_token', ['family_id'], unique=False)
    op.add_column(
        'user',
        sa.Column('tokens_valid_after', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('user', 'tokens_valid_after')
    op.drop_index(op.f('ix_refresh_token_family_id'), table_name='refresh_token')
    op.drop_column('refresh_token', 'family_id')
