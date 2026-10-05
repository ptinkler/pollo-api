"""add chat_instructions table and chat_conversations.instruction_id

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-05

Saved custom instructions for chat mode, attachable per conversation.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # MetadataDB() creates tables / adds this column on startup too, so each
    # step is skipped if it already happened.
    insp = sa.inspect(op.get_bind())
    if "chat_instructions" not in insp.get_table_names():
        op.create_table(
            "chat_instructions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    if "instruction_id" not in {c["name"] for c in insp.get_columns("chat_conversations")}:
        with op.batch_alter_table("chat_conversations") as batch_op:
            batch_op.add_column(sa.Column("instruction_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("chat_conversations") as batch_op:
        batch_op.drop_column("instruction_id")
    op.drop_table("chat_instructions")
