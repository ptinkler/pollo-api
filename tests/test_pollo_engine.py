"""Snapshot regression tests for the data-driven Pollo payload engine.

The engine was built and verified byte-identical to the old generator-class
hierarchy (the oracle) via an old-vs-new harness; `tests/data/
pollo_payloads_golden.json` pins that proven output. Each engine family builder
must keep producing exactly those payloads / model URLs (and the same errors on
invalid inputs). Regenerate the golden only on a deliberate, reviewed change.
"""

import json
from pathlib import Path

import pytest

from web.providers import pollo_engine as eng

pytestmark = pytest.mark.no_tenant

GOLDEN = json.loads((Path(__file__).parent / "data" / "pollo_payloads_golden.json").read_text())

# section -> (payload builder, model-url builder)
_FN = {
    "v1_video": (eng.v1_video_payload, eng.v1_video_model_url),
    "v1_image": (eng.v1_image_payload, eng.v1_image_model_url),
    "legacy_video": (eng.legacy_video_payload, eng.legacy_video_model_url),
    "legacy_image": (eng.legacy_image_payload, eng.legacy_image_model_url),
    "legacy_ref": (eng.legacy_ref_payload, eng.legacy_ref_model_url),
}

_PARAMS = [(section, mid) for section, models in GOLDEN.items() for mid in models]


def test_golden_covers_every_registered_model():
    """The golden snapshot must list exactly the models the registries expose."""
    assert set(GOLDEN["v1_video"]) == set(eng.V1_VIDEO)
    assert set(GOLDEN["v1_image"]) == set(eng.V1_IMAGE)
    assert set(GOLDEN["legacy_video"]) == set(eng.LEGACY_VIDEO)
    assert set(GOLDEN["legacy_image"]) == set(eng.LEGACY_IMAGE)
    assert set(GOLDEN["legacy_ref"]) == set(eng.LEGACY_REF)


@pytest.mark.parametrize("section,model_id", _PARAMS)
def test_engine_payload_matches_golden(section, model_id):
    build, model_url = _FN[section]
    data = GOLDEN[section][model_id]
    assert model_url(model_id) == data["url"], f"url mismatch: {model_id}"
    for c in data["cases"]:
        try:
            got = {"ok": build(model_id, **c["kw"])}
        except Exception as exc:  # noqa: BLE001
            got = {"error": type(exc).__name__}
        expected = {"ok": c["ok"]} if "ok" in c else {"error": c["error"]}
        assert got == expected, f"mismatch: {model_id} {c['kw']}\n got={got}\n want={expected}"
