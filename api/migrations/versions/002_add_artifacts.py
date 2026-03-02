"""Add chat_artifacts table

Revision ID: 002
Revises: 001
Create Date: 2026-03-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'chat_artifacts',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('chat_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('name', sa.String(512), nullable=False),
        sa.Column('kind', sa.String(50), nullable=False),
        sa.Column('size', sa.BigInteger(), nullable=True),
        sa.Column('url', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['chat_id'], ['chat_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_chat_artifacts_chat_id', 'chat_artifacts', ['chat_id'])


def downgrade() -> None:
    op.drop_index('ix_chat_artifacts_chat_id', table_name='chat_artifacts')
    op.drop_table('chat_artifacts')
