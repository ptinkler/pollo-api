"""add chat_conversations and chat_messages tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-25

Backs the OpenRouter chat mode (web/chat.py).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # MetadataDB() runs create_all() on startup, so the tables may already
    # exist if the app ran before this migration — skip them in that case.
    existing = set(sa.inspect(op.get_bind()).get_table_names())

    if "chat_conversations" not in existing:
        op.create_table(
            "chat_conversations",
            sa.Column("id", sa.String(50), primary_key=True),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("text_model", sa.String(255), nullable=True),
            sa.Column("image_model", sa.String(255), nullable=True),
            sa.Column("video_model", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_chat_conversations_updated_at", "chat_conversations", ["updated_at"])

    if "chat_messages" not in existing:
        op.create_table(
            "chat_messages",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("conversation_id", sa.String(50),
                      sa.ForeignKey("chat_conversations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("role", sa.String(20), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("media_json", sa.Text(), nullable=True),
            sa.Column("model", sa.String(255), nullable=True),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("cost", sa.Float(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_chat_messages_conversation_id", "chat_messages", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_messages_conversation_id", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("ix_chat_conversations_updated_at", table_name="chat_conversations")
    op.drop_table("chat_conversations")
