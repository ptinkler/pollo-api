"""Snapshot regression tests for the data-driven Pollo payload engine.

The engine was built and verified byte-identical to the old generator-class
hierarchy (the oracle) via an old-vs-new harness; `tests/data/
pollo_payloads_golden.json` pins that proven output. Each builder must keep
producing exactly those payloads / model URLs (and the same errors on invalid
inputs). Regenerate the golden only on a deliberate, reviewed change.
"""

import json
from pathlib import Path

import pytest

from web.providers import pollo_engine as eng

pytestmark = pytest.mark.no_tenant

GOLDEN = json.loads((Path(__file__).parent / "data" / "pollo_payloads_golden.json").read_text())

# kind -> (payload builder, model-url builder)
_FN = {
    "video": (eng.video_payload, eng.video_model_url),
    "image": (eng.image_payload, eng.image_model_url),
    "audio": (eng.audio_payload, eng.audio_model_url),
}

_PARAMS = [(kind, mid) for kind, models in GOLDEN.items() for mid in models]


def test_golden_covers_every_registered_model():
    """The golden snapshot must list exactly the models the tables expose."""
    assert set(GOLDEN["video"]) == set(eng.VIDEO_MODELS)
    assert set(GOLDEN["image"]) == set(eng.IMAGE_MODELS)
    assert set(GOLDEN["audio"]) == set(eng.AUDIO_MODELS)


@pytest.mark.parametrize(("kind", "model_id"), _PARAMS)
def test_engine_payload_matches_golden(kind, model_id):
    """Test that engine payload matches golden."""
    build, model_url = _FN[kind]
    data = GOLDEN[kind][model_id]
    assert model_url(model_id) == data["url"], f"url mismatch: {model_id}"
    for c in data["cases"]:
        try:
            got = {"ok": build(model_id, **c["kw"])}
        except Exception as exc:
            got = {"error": type(exc).__name__}
        expected = {"ok": c["ok"]} if "ok" in c else {"error": c["error"]}
        assert got == expected, f"mismatch: {model_id} {c['kw']}\n got={got}\n want={expected}"
