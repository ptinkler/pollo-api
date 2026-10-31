"""add thread kind, and split favourite from pinned on chat media

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-31

Two related changes for the Studio overhaul:

  • chat_conversations.kind ("chat" | "gallery") — which view a thread opens
    on. Threads migrated from Generate projects (import_source =
    'migrated-project') default to "gallery"; everything else to "chat".

  • A media item's "pinned" flag used to serve double duty: a *reference*
    image re-sent with every new generation, AND (historically, via 0018) a
    user *favourite*. Those are now distinct — "favourite" is a new flag. This
    backfills favourite=true onto every media item currently pinned, so
    existing favourites still appear in the new Favourites gallery. Pinning
    (the reference behaviour) is left untouched.

Idempotent: the column add is skipped if present, and the favourite backfill
only ever sets the flag (re-running changes nothing new).

Downgrade drops the kind column and removes the favourite flag again.
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

revision: str = "0022"
down_revision: str | Sequence[str] | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _set_favourite_from_pinned(items: list) -> bool:
    """Mark pinned items as favourites. Returns True if anything changed."""
    changed = False
    for item in items:
        if item.get("pinned") and not item.get("favourite"):
            item["favourite"] = True
            changed = True
    return changed


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    existing = {c["name"] for c in insp.get_columns("chat_conversations")}
    if "kind" not in existing:
        with op.batch_alter_table("chat_conversations") as batch_op:
            batch_op.add_column(sa.Column("kind", sa.String(10), nullable=False, server_default="chat"))

    # Threads folded in from Generate projects are galleries of generations
    op.execute(sa.text("UPDATE chat_conversations SET kind = 'gallery' WHERE import_source = 'migrated-project'"))

    # Backfill favourite=true wherever a media item is currently pinned.
    session = Session(bind=bind)
    try:
        for mid, media_json in session.execute(
            sa.text("SELECT id, media_json FROM chat_messages WHERE media_json LIKE '%\"pinned\"%'")
        ).all():
            try:
                items = json.loads(media_json) if media_json else []
            except (json.JSONDecodeError, TypeError):
                continue
            if _set_favourite_from_pinned(items):
                session.execute(
                    sa.text("UPDATE chat_messages SET media_json = :j WHERE id = :id"),
                    {"j": json.dumps(items), "id": mid},
                )
        for lid, item_json in session.execute(
            sa.text("SELECT id, item_json FROM chat_library_items WHERE item_json LIKE '%\"pinned\"%'")
        ).all():
            try:
                item = json.loads(item_json) if item_json else {}
            except (json.JSONDecodeError, TypeError):
                continue
            if item.get("pinned") and not item.get("favourite"):
                item["favourite"] = True
                session.execute(
                    sa.text("UPDATE chat_library_items SET item_json = :j WHERE id = :id"),
                    {"j": json.dumps(item), "id": lid},
                )
        session.commit()
    finally:
        session.close()


def downgrade() -> None:
    bind = op.get_bind()
    with op.batch_alter_table("chat_conversations") as batch_op:
        batch_op.drop_column("kind")

    session = Session(bind=bind)
    try:
        for mid, media_json in session.execute(
            sa.text("SELECT id, media_json FROM chat_messages WHERE media_json LIKE '%\"favourite\"%'")
        ).all():
            try:
                items = json.loads(media_json) if media_json else []
            except (json.JSONDecodeError, TypeError):
                continue
            changed = False
            for item in items:
                if "favourite" in item:
                    del item["favourite"]
                    changed = True
            if changed:
                session.execute(
                    sa.text("UPDATE chat_messages SET media_json = :j WHERE id = :id"),
                    {"j": json.dumps(items), "id": mid},
                )
        session.commit()
    finally:
        session.close()
