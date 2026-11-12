"""strip the v1 suffix from stored Pollo model ids.

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-10

Pollo's legacy (pre-v1) endpoints are gone, so the engine's model keys no
longer need to say which API generation they belong to: "seedance20fastv1"
is now "seedance20fast". Those keys are stored as "pollo/<key>" wherever a
generation recorded which model made it, so rewrite them in place.

The ids are labels on past work — history, the composer's remembered picks —
so this is cosmetic, but leaving them stale would show "unknown model" on old
cards and lose a thread's model selection.

Note: a few renamed keys match ids that belonged to the removed legacy models
of the same name (legacy "seedance20fast" and v1 "seedance20fastv1" both end
up "seedance20fast"). Those are the same model on a different endpoint, so
history pointing at the surviving one is right.

Ids of models that were removed outright with the legacy endpoints (Pollo
Image 2.0, Qwen Image) are deliberately left as they are: they record what
actually made that image, so the card shows the bare key rather than a label.
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection

type _JsonValue = str | int | float | bool | list[_JsonValue] | dict[str, _JsonValue] | None

revision: str = "0027"
down_revision: str | Sequence[str] | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PREFIX = "pollo/"
SUFFIX = "v1"
# Plain string columns holding one model id
_COLUMNS = [
    ("chat_conversations", "text_model"),
    ("chat_conversations", "image_model"),
    ("chat_conversations", "video_model"),
    ("chat_messages", "model"),
    ("chat_settings", "title_model"),
]
# JSON columns: (table, column, whether the JSON is a list of media items)
_JSON_COLUMNS = [
    ("chat_messages", "media_json", True),  # [ {model: …}, … ]
    ("chat_library_items", "item_json", False),  # { model: … }
    ("chat_conversations", "settings_json", False),  # { audio_model: … }
]
_JSON_KEYS = ("model", "audio_model", "text_model", "image_model", "video_model")


def _renamed(value: _JsonValue, to_v1: bool) -> _JsonValue:
    """One model id, with the v1 suffix stripped (or put back on a downgrade).

    Anything that isn't a suffixed Pollo id is returned unchanged.
    """
    if not isinstance(value, str) or not value.startswith(PREFIX):
        return value
    key = value[len(PREFIX) :]
    if to_v1:
        return value if key.endswith(SUFFIX) else f"{PREFIX}{key}{SUFFIX}"
    return f"{PREFIX}{key[: -len(SUFFIX)]}" if key.endswith(SUFFIX) else value


def _walk(data: _JsonValue, to_v1: bool) -> bool:
    """Rewrite every model id in a decoded JSON value; True if anything changed."""
    changed = False
    if isinstance(data, list):
        for item in data:
            changed |= _walk(item, to_v1)
    elif isinstance(data, dict):
        for key, value in data.items():
            if key in _JSON_KEYS:
                new = _renamed(value, to_v1)
                if new != value:
                    data[key] = new
                    changed = True
            elif isinstance(value, list | dict):
                changed |= _walk(value, to_v1)
    return changed


def rewrite(bind: Connection, to_v1: bool = False) -> int:
    """Rewrite every stored Pollo model id; returns how many rows changed.

    Takes the bind so it can be tested without an Alembic context.
    """
    changed_rows = 0
    tables = set(sa.inspect(bind).get_table_names())

    for table, column in _COLUMNS:
        if table not in tables:
            continue
        rows = bind.execute(
            sa.text(f"SELECT rowid, {column} FROM {table} WHERE {column} LIKE :p"), {"p": f"{PREFIX}%"}
        ).all()
        for rowid, value in rows:
            new = _renamed(value, to_v1)
            if new != value:
                bind.execute(sa.text(f"UPDATE {table} SET {column} = :v WHERE rowid = :r"), {"v": new, "r": rowid})
                changed_rows += 1

    for table, column, _is_list in _JSON_COLUMNS:
        if table not in tables:
            continue
        rows = bind.execute(
            sa.text(f"SELECT rowid, {column} FROM {table} WHERE {column} LIKE :p"), {"p": f"%{PREFIX}%"}
        ).all()
        for rowid, raw in rows:
            try:
                data = json.loads(raw)
            except (TypeError, ValueError):
                continue  # not readable JSON: leave it exactly as it is
            if _walk(data, to_v1):
                bind.execute(
                    sa.text(f"UPDATE {table} SET {column} = :v WHERE rowid = :r"),
                    {"v": json.dumps(data), "r": rowid},
                )
                changed_rows += 1
    return changed_rows


def upgrade() -> None:
    """Remove the v1 suffix from stored Pollo model IDs."""
    rewrite(op.get_bind(), to_v1=False)


def downgrade() -> None:
    """Restore the v1 suffix to stored Pollo model IDs."""
    rewrite(op.get_bind(), to_v1=True)
