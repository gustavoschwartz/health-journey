"""add source to sync_log

Revision ID: 18b2e5ddbeea
Revises: 31dd7e1db80a
Create Date: 2026-06-11 14:16:42.687610

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '18b2e5ddbeea'
down_revision: Union[str, Sequence[str], None] = '31dd7e1db80a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


sync_source_enum = sa.Enum(
    'strava', 'apple_health', 'vesync', 'omron',
    name='syncsourceenum'
)


def upgrade() -> None:
    """Upgrade schema."""
    sync_source_enum.create(op.get_bind())
    # server_default backfills existing rows (all Strava today) and keeps
    # already-deployed code working until it also stamps source explicitly
    op.add_column('sync_log', sa.Column(
        'source', sync_source_enum,
        nullable=False, server_default='strava'
    ))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('sync_log', 'source')
    sync_source_enum.drop(op.get_bind())
