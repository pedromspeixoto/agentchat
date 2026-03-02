"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'chat_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('title', sa.String(255), nullable=True),
        sa.Column('sdk_session_id', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_chat_sessions_sdk_session_id', 'chat_sessions', ['sdk_session_id'])

    op.create_table(
        'chat_messages',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('chat_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('role', sa.String(50), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('message_metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['chat_id'], ['chat_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_chat_messages_chat_id', 'chat_messages', ['chat_id'])

    op.create_table(
        'chat_usage',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('chat_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=False),
        sa.Column('output_tokens', sa.Integer(), nullable=False),
        sa.Column('total_tokens', sa.Integer(), nullable=False),
        sa.Column('cost_usd', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['chat_id'], ['chat_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_chat_usage_chat_id', 'chat_usage', ['chat_id'])

    op.create_table(
        'chat_events',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('chat_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('message_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('event_name', sa.String(255), nullable=True),
        sa.Column('event_data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['chat_id'], ['chat_sessions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['message_id'], ['chat_messages.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_chat_events_chat_id', 'chat_events', ['chat_id'])
    op.create_index('ix_chat_events_message_id', 'chat_events', ['message_id'])
    op.create_index('ix_chat_events_event_type', 'chat_events', ['event_type'])


def downgrade() -> None:
    op.drop_table('chat_events')
    op.drop_table('chat_usage')
    op.drop_table('chat_messages')
    op.drop_table('chat_sessions')
