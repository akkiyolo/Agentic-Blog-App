"""add auto tagging fields

Revision ID: e6ea52c81388
Revises: cdfbf5f19390
Create Date: 2026-08-08 09:36:19.423971

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6ea52c81388'
down_revision: Union[str, Sequence[str], None] = 'cdfbf5f19390'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('posts', sa.Column('tags', sa.ARRAY(sa.String()), nullable=True))
    op.add_column('posts', sa.Column('summary', sa.Text(), nullable=True))
    op.add_column('posts', sa.Column('meta_description', sa.String(length=160), nullable=True))
    op.add_column(
        'posts',
        sa.Column('tagging_status', sa.String(length=20), server_default='pending', nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('posts', 'tagging_status')
    op.drop_column('posts', 'meta_description')
    op.drop_column('posts', 'summary')
    op.drop_column('posts', 'tags')
