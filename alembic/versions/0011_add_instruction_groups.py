"""add instruction groups and multi-snippet chat attachments

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-15

Instructions become snippets that can be bundled into named groups. A chat now
attaches any number of snippets and groups (both as JSON id lists), flattened
and de-duped into what the model is sent. The old single chat_conversations.
instruction_id is carried into instruction_ids_json. Only one thing — a snippet
or a group — is the default attached to new chats.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = [
    sa.Column("instruction_ids_json", sa.Text(), nullable=True),
    sa.Column("instruction_group_ids_json", sa.Text(), nullable=True),
]


def upgrade() -> None:
    # MetadataDB() creates this table / adds these columns on startup too, so
    # each step is skipped if it already happened.
    insp = sa.inspect(op.get_bind())
    if "chat_instruction_groups" not in insp.get_table_names():
        op.create_table(
            "chat_instruction_groups",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("snippet_ids_json", sa.Text(), nullable=True),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    existing = {c["name"] for c in insp.get_columns("chat_conversations")}
    with op.batch_alter_table("chat_conversations") as batch_op:
        for col in COLUMNS:
            if col.name not in existing:
                batch_op.add_column(col)
    # Carry the old single attachment into the new list
    if "instruction_ids_json" not in existing:
        op.execute(
            "UPDATE chat_conversations SET instruction_ids_json = '[' || instruction_id || ']' "
            "WHERE instruction_id IS NOT NULL AND instruction_ids_json IS NULL"
        )


def downgrade() -> None:
    with op.batch_alter_table("chat_conversations") as batch_op:
        for col in reversed(COLUMNS):
            batch_op.drop_column(col.name)
    op.drop_table("chat_instruction_groups")
