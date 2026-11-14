"""add text_versions_json to chat_messages.

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-14

A reply's earlier wordings, kept when only its text is written again (Edit
text / Redo text), so the < > arrows on the text can flip between them while
its pictures stay as they are. Shape: {"items": [{"content", "model"}], "shown": i}.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: str | Sequence[str] | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add text versions to chat messages."""
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("chat_messages")}
    if "text_versions_json" not in existing:
        with op.batch_alter_table("chat_messages") as batch_op:
            batch_op.add_column(sa.Column("text_versions_json", sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove text versions from chat messages."""
    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.drop_column("text_versions_json")
