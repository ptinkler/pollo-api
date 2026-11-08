"""move pure-gallery threads' exchanges into the gallery lane

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-08

Before lanes, a gallery thread's generations were ordinary chat turns. For a
thread with kind='gallery' whose every prompt ran in image/video mode, each
exchange becomes a standalone gallery exchange (lane='gallery', prompt parent
cleared), so the chat view starts clean and the gallery still shows them all.
Threads with any text/auto turn are left alone — their chat history is real.
Downgrade is a no-op (the original parent links are not kept).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | Sequence[str] | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def backfill(conn) -> int:
    """Returns how many conversations were converted."""
    convs = conn.execute(sa.text("SELECT id FROM chat_conversations WHERE kind = 'gallery'")).scalars().all()
    done = 0
    for cid in convs:
        rows = conn.execute(
            sa.text("SELECT id, role, mode, lane FROM chat_messages WHERE conversation_id = :c"), {"c": cid}
        ).all()
        users = [r for r in rows if r.role == "user"]
        if not users or any(r.lane for r in rows) or any(r.mode not in ("image", "video") for r in users):
            continue
        conn.execute(sa.text("UPDATE chat_messages SET lane = 'gallery' WHERE conversation_id = :c"), {"c": cid})
        # Each prompt starts its own exchange; replies stay under their prompt
        conn.execute(
            sa.text("UPDATE chat_messages SET parent_id = NULL WHERE conversation_id = :c AND role = 'user'"),
            {"c": cid},
        )
        conn.execute(sa.text("UPDATE chat_conversations SET current_leaf_id = NULL WHERE id = :c"), {"c": cid})
        done += 1
    return done


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("chat_messages") and insp.has_table("chat_conversations"):
        backfill(bind)


def downgrade() -> None:
    pass
