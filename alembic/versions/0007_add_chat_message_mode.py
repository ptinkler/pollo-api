"""add chat_messages.mode

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-06

The composer mode a chat turn ran in, so editing or retrying it reruns it
the same way (e.g. a Video-mode prompt stays a video).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # MetadataDB() adds this column on startup too, so skip it if it's there
    if "mode" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("chat_messages")}:
        with op.batch_alter_table("chat_messages") as batch_op:
            batch_op.add_column(sa.Column("mode", sa.String(10), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.drop_column("mode")
