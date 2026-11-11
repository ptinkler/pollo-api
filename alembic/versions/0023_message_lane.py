"""add chat_messages.lane (standalone gallery exchanges beside the chat).

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | Sequence[str] | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("chat_messages")}
    if "lane" not in existing:
        with op.batch_alter_table("chat_messages") as batch_op:
            batch_op.add_column(sa.Column("lane", sa.String(10), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.drop_column("lane")
