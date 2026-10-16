"""chat defaults apply live: take the copies of them out of existing chats

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-16

The global and space defaults (characters, instruction snippets and groups)
used to be copied into a chat when it was made; now they apply to every chat
live, on top of what's attached to the chat itself (web/chat.py _inherited).
So each chat's own lists lose the ids its defaults now supply — otherwise
taking something out of the defaults would leave it in every older chat.
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS = ("character", "instruction", "instruction_group")


def _ids(raw: str | None) -> list:
    try:
        return json.loads(raw) if raw else []
    except json.JSONDecodeError:
        return []


def upgrade() -> None:
    bind = op.get_bind()
    cols = ", ".join(f"default_{k}_ids_json" for k in KINDS)
    glob = bind.execute(sa.text(f"SELECT {cols} FROM chat_settings WHERE id = 1")).first()
    spaces = {row[0]: row[1:] for row in bind.execute(sa.text(f"SELECT id, {cols} FROM chat_spaces"))}
    own_cols = ", ".join(f"{k}_ids_json" for k in KINDS)
    for conv_id, space_id, *own in bind.execute(
        sa.text(f"SELECT id, space_id, {own_cols} FROM chat_conversations")
    ).all():
        buckets = [b for b in (glob, spaces.get(space_id)) if b]
        changes = {}
        for i, kind in enumerate(KINDS):
            inherited = {x for b in buckets for x in _ids(b[i])}
            ids = _ids(own[i])
            kept = [x for x in ids if x not in inherited]
            if kept != ids:
                changes[f"{kind}_ids_json"] = json.dumps(kept)
        if changes:
            sets = ", ".join(f"{c} = :{c}" for c in changes)
            bind.execute(sa.text(f"UPDATE chat_conversations SET {sets} WHERE id = :id"), {**changes, "id": conv_id})


def downgrade() -> None:
    pass  # the copies can't be told apart from what was attached by hand
