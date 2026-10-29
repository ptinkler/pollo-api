"""multi-tenant: add user_id to tenant tables and backfill to the admin

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-28

Every tenant-owned row gets a user_id. Existing rows (created before login
existed) are assigned to the admin — the instance owner — so nothing is
orphaned and nothing leaks to other users once scoping is enforced.
"""

import os
import uuid
from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | Sequence[str] | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = [
    "projects",
    "downloads",
    "jobs",
    "generation_favourites",
    "chat_conversations",
    "characters",
    "chat_instructions",
    "chat_instruction_groups",
    "chat_spaces",
    "chat_settings",
    "chat_messages",
    "chat_library_items",
    "chat_import_skips",
]


def _admin_id(conn) -> str:
    # The admin is keyed on email (ADMIN_EMAILS), so the backfill lands on the
    # same account the owner later signs into with Google or the access key.
    email = next((e.strip() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()), "admin@local")
    row = conn.execute(sa.text("SELECT id FROM users WHERE email = :email"), {"email": email}).fetchone()
    if row:
        return row[0]
    admin_id = uuid.uuid4().hex
    conn.execute(
        sa.text(
            "INSERT INTO users (id, email, name, provider, provider_sub, is_admin, created_at) "
            "VALUES (:id, :email, 'Admin', 'local', 'admin', 1, :now)"
        ),
        {"id": admin_id, "email": email, "now": datetime.now()},
    )
    return admin_id


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    admin_id = _admin_id(bind)
    for table in TENANT_TABLES:
        cols = {c["name"] for c in insp.get_columns(table)}
        if "user_id" not in cols:
            with op.batch_alter_table(table) as batch_op:
                batch_op.add_column(sa.Column("user_id", sa.String(length=50), nullable=True))
                batch_op.create_index(f"ix_{table}_user_id", ["user_id"])
        # Backfill existing rows to the admin
        bind.execute(sa.text(f"UPDATE {table} SET user_id = :uid WHERE user_id IS NULL"), {"uid": admin_id})


def downgrade() -> None:
    for table in TENANT_TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_index(f"ix_{table}_user_id")
            batch_op.drop_column("user_id")
