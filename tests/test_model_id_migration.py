"""Migration 0027: stripping the v1 suffix from stored Pollo model ids.

The ids live in plain columns and inside JSON, so the rewrite has to reach
every place a generation recorded which model made it — and leave every other
provider's ids (and unreadable JSON) untouched.
"""

import importlib.util
import json
from pathlib import Path

import pytest
import sqlalchemy as sa

pytestmark = pytest.mark.no_tenant


def _migration():
    path = Path(__file__).parent.parent / "alembic" / "versions" / "0027_drop_pollo_v1_suffix.py"
    spec = importlib.util.spec_from_file_location("m0027", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def bind():
    eng = sa.create_engine("sqlite://")
    with eng.begin() as c:
        c.execute(
            sa.text(
                "CREATE TABLE chat_conversations (id TEXT, text_model TEXT, image_model TEXT,"
                " video_model TEXT, settings_json TEXT)"
            )
        )
        c.execute(sa.text("CREATE TABLE chat_messages (id INTEGER PRIMARY KEY, model TEXT, media_json TEXT)"))
        c.execute(sa.text("CREATE TABLE chat_library_items (id TEXT, item_json TEXT)"))
        c.execute(sa.text("CREATE TABLE chat_settings (id INTEGER PRIMARY KEY, title_model TEXT)"))
        yield c


def test_rewrites_every_stored_id(bind):
    mod = _migration()
    bind.execute(
        sa.text(
            "INSERT INTO chat_conversations VALUES ('c', 'anthropic/claude', 'pollo/seedreamv1',"
            " 'pollo/seedance20fastv1', :s)"
        ),
        {"s": json.dumps({"audio_model": "pollo/elevenv3v1", "image_options": {"resolution": "1K"}})},
    )
    bind.execute(
        sa.text("INSERT INTO chat_messages VALUES (1, 'pollo/pollo30v1', :m)"),
        {
            "m": json.dumps(
                [
                    {"id": "a", "kind": "image", "model": "pollo/seedreamprov1", "prompt": "a fox"},
                    {"id": "b", "kind": "video", "model": "venice/wan-2-5", "params": {"duration": 5}},
                ]
            )
        },
    )
    bind.execute(
        sa.text("INSERT INTO chat_library_items VALUES ('x', :i)"),
        {"i": json.dumps({"id": "x", "model": "pollo/klingv3imagev1"})},
    )
    bind.execute(sa.text("INSERT INTO chat_settings VALUES (1, 'pollo/pollo30v1')"))

    # one update per column touched: image_model, video_model, settings_json,
    # chat_messages.model, media_json, item_json, title_model
    assert mod.rewrite(bind) == 7

    conv = bind.execute(sa.text("SELECT * FROM chat_conversations")).mappings().one()
    assert conv["image_model"] == "pollo/seedream"
    assert conv["video_model"] == "pollo/seedance20fast"
    assert conv["text_model"] == "anthropic/claude"  # another provider's id is left alone
    assert json.loads(conv["settings_json"]) == {
        "audio_model": "pollo/elevenv3",
        "image_options": {"resolution": "1K"},
    }

    msg = bind.execute(sa.text("SELECT * FROM chat_messages")).mappings().one()
    assert msg["model"] == "pollo/pollo30"
    media = json.loads(msg["media_json"])
    assert media[0]["model"] == "pollo/seedreampro"
    assert media[1]["model"] == "venice/wan-2-5"
    assert media[1]["params"] == {"duration": 5}  # nothing else in the item is touched

    lib = bind.execute(sa.text("SELECT item_json FROM chat_library_items")).scalar()
    assert json.loads(lib)["model"] == "pollo/klingv3image"
    assert bind.execute(sa.text("SELECT title_model FROM chat_settings")).scalar() == "pollo/pollo30"


def test_is_idempotent_and_reversible(bind):
    mod = _migration()
    bind.execute(sa.text("INSERT INTO chat_conversations VALUES ('c', NULL, 'pollo/seedreamv1', NULL, NULL)"))
    assert mod.rewrite(bind) == 1
    assert mod.rewrite(bind) == 0  # a second run has nothing left to do
    assert bind.execute(sa.text("SELECT image_model FROM chat_conversations")).scalar() == "pollo/seedream"
    mod.rewrite(bind, to_v1=True)  # downgrade
    assert bind.execute(sa.text("SELECT image_model FROM chat_conversations")).scalar() == "pollo/seedreamv1"


def test_leaves_unreadable_json_alone(bind):
    mod = _migration()
    bind.execute(sa.text("INSERT INTO chat_messages VALUES (1, NULL, 'pollo/ not json {')"))
    assert mod.rewrite(bind) == 0
    assert bind.execute(sa.text("SELECT media_json FROM chat_messages")).scalar() == "pollo/ not json {"


def test_skips_tables_that_do_not_exist_yet():
    """An older database may predate some of these tables."""
    mod = _migration()
    eng = sa.create_engine("sqlite://")
    with eng.begin() as c:
        c.execute(sa.text("CREATE TABLE chat_messages (id INTEGER PRIMARY KEY, model TEXT, media_json TEXT)"))
        c.execute(sa.text("INSERT INTO chat_messages VALUES (1, 'pollo/pollo30v1', NULL)"))
        assert mod.rewrite(c) == 1
