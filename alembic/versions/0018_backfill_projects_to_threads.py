"""backfill Generate projects into the unified thread model.

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-28

Originally a one-time data migration that folded each Generate-page project +
its successful jobs into the thread model. That ran on every deployment before
the legacy generation subsystem (projects/jobs/downloads/favourites tables +
models) was removed, so there is nothing left to backfill and the data step is
retired. What remains are the defensive column-adds that later migrations
(0020 user_id, 0022 kind) expect to already be present — kept and guarded so a
fresh database still migrates cleanly; they skip tables that no longer exist.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

IMPORT_SOURCE = "migrated-project"


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    # Columns later migrations expect (0020 adds user_id, 0022 adds kind); both
    # are guarded and skip what's already present. Legacy tables are skipped
    # entirely when absent (they were removed with the generation subsystem).
    for table in ("projects", "jobs", "downloads", "generation_favourites", "chat_conversations", "chat_messages"):
        if insp.has_table(table) and "user_id" not in {c["name"] for c in insp.get_columns(table)}:
            op.execute(f"ALTER TABLE {table} ADD COLUMN user_id VARCHAR(50)")
    if "kind" not in {c["name"] for c in insp.get_columns("chat_conversations")}:
        op.execute("ALTER TABLE chat_conversations ADD COLUMN kind VARCHAR(10) NOT NULL DEFAULT 'chat'")


def downgrade() -> None:
    # Remove any threads the original backfill created (by raw SQL, since the
    # ORM models are gone).
    bind = op.get_bind()
    bind.exec_driver_sql(
        "DELETE FROM chat_messages WHERE conversation_id IN "
        f"(SELECT id FROM chat_conversations WHERE import_source = '{IMPORT_SOURCE}')"
    )
    bind.exec_driver_sql(f"DELETE FROM chat_conversations WHERE import_source = '{IMPORT_SOURCE}'")
