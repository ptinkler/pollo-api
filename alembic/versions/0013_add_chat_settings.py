"""add global chat settings (default buckets)

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-15

Global chat defaults move from the per-snippet/group `is_default` flag into a
single chat_settings row (id=1) holding default character/snippet/group id
lists. A space's own defaults stack on top of these. The old is_default columns
are left in place (unused) and their data is carried into chat_settings.
"""

import json
from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "chat_settings" not in insp.get_table_names():
        op.create_table(
            "chat_settings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("default_character_ids_json", sa.Text(), nullable=True),
            sa.Column("default_instruction_ids_json", sa.Text(), nullable=True),
            sa.Column("default_instruction_group_ids_json", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    if bind.execute(sa.text("SELECT 1 FROM chat_settings WHERE id = 1")).first():
        return
    # Carry the old is_default flags into the global bucket
    values = {}
    for field, table in (
        ("default_instruction_ids_json", "chat_instructions"),
        ("default_instruction_group_ids_json", "chat_instruction_groups"),
    ):
        if insp.has_table(table) and "is_default" in {c["name"] for c in insp.get_columns(table)}:
            ids = [r[0] for r in bind.execute(sa.text(f"SELECT id FROM {table} WHERE is_default = 1"))]
            if ids:
                values[field] = json.dumps(ids)
    cols = ", ".join(["id", "updated_at", *values])
    placeholders = ", ".join(["1", ":updated_at", *(f":{k}" for k in values)])
    bind.execute(
        sa.text(f"INSERT INTO chat_settings ({cols}) VALUES ({placeholders})"),
        {"updated_at": datetime.now(), **values},
    )


def downgrade() -> None:
    op.drop_table("chat_settings")
