"""add characters

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-07

Reusable characters (name, description, reference images) shared by chat
and generations, plus the characters attached to each chat.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0009'
down_revision: Union[str, Sequence[str], None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # MetadataDB() creates tables/columns on startup too, so skip what's there
    insp = sa.inspect(op.get_bind())
    if "characters" not in insp.get_table_names():
        op.create_table(
            "characters",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("images_json", sa.Text(), nullable=True),
            sa.Column("conversation_id", sa.String(50), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_characters_conversation_id", "characters", ["conversation_id"])
    if "character_ids_json" not in {c["name"] for c in insp.get_columns("chat_conversations")}:
        op.add_column("chat_conversations", sa.Column("character_ids_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("chat_conversations", "character_ids_json")
    op.drop_index("ix_characters_conversation_id", table_name="characters")
    op.drop_table("characters")
