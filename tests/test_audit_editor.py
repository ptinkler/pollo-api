"""The audit's --write editor: it must make only the intended surgical change
to a model entry and leave everything else (including curated fields) intact.
"""

import ast

import pytest

from scripts import audit_pollo_models as audit


def _model_info(src: str) -> dict:
    """The MODEL_INFO literal from generated source, parsed rather than run.

    Proves the output is valid Python and reads the value back without
    executing it, which exec would.
    """
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "MODEL_INFO" for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("generated source defines no MODEL_INFO")


pytestmark = pytest.mark.no_tenant

SAMPLE = """MODEL_INFO = {
    "alpha": {
        "label": "Alpha",
        "type": "img2vid",
        "hidden": "Not enabled for API access on this key (403)",  # old
        "options": ["image_tail"],
    },
    "beta": {
        "label": "Beta",
        "type": "img2vid",
        "ref_mode": {
            "types": ["image", "video"],
            "max": 7,
            "limits": {"image": 4, "video": 1},
            "no_audio_with_video": True,
        },
    },
}
"""


def _write_apply(tmp_path, edits):
    f = tmp_path / "m.py"
    f.write_text(SAMPLE, encoding="utf-8")
    warnings = []
    n = audit.apply_edits(str(f), edits, warnings)
    return f.read_text(encoding="utf-8"), n, warnings


def test_py_literal_double_quotes_and_bools():
    assert audit.py_literal({"types": ["image"], "max": 7, "no_audio_with_video": True}) == (
        '{"types": ["image"], "max": 7, "no_audio_with_video": True}'
    )


def test_remove_hidden_leaves_rest(tmp_path):
    out, n, warns = _write_apply(tmp_path, {"alpha": {"hidden": audit._REMOVE}})
    assert n == 1
    assert not warns
    assert '"hidden"' not in out.split('"beta"')[0]  # alpha's hidden gone
    assert '"label": "Alpha"' in out
    assert '"options": ["image_tail"]' in out


def test_insert_field(tmp_path):
    out, n, _ = _write_apply(tmp_path, {"alpha": {"ref_mode": '{"types": ["image"], "max": 3}'}})
    assert n == 1
    assert '"ref_mode": {"types": ["image"], "max": 3},' in out
    # still valid Python
    assert _model_info(out)["alpha"]["ref_mode"] == {"types": ["image"], "max": 3}


def test_replace_multiline_refmode_preserving_curated(tmp_path):
    # The caller merges; here we just prove a multi-line value is replaced wholesale.
    merged = audit.py_literal(
        {"types": ["image", "video"], "max": 15, "limits": {"image": 10, "video": 5}, "no_audio_with_video": True}
    )
    out, n, warns = _write_apply(tmp_path, {"beta": {"ref_mode": merged}})
    assert n == 1
    assert not warns
    rm = _model_info(out)["beta"]["ref_mode"]
    assert rm["max"] == 15
    assert rm["limits"]["image"] == 10
    assert rm["no_audio_with_video"] is True


def test_value_with_trailing_comment_stays_valid(tmp_path):
    # The comma must land before the comment, not inside it.
    val = '"Not enabled for API access (403)"  # 2026-11-09 probe'
    out, n, _ = _write_apply(tmp_path, {"alpha": {"hidden": val}})
    assert n == 1
    assert '"hidden": "Not enabled for API access (403)",  # 2026-11-09 probe' in out
    assert _model_info(out)["alpha"]["hidden"] == "Not enabled for API access (403)"


def test_one_line_inline_entry(tmp_path):
    src = 'MODEL_INFO = {\n    "inline": {"label": "In", "type": "motion", "video_input": True},\n}\n'
    f = tmp_path / "m.py"
    f.write_text(src, encoding="utf-8")
    warnings = []
    n = audit.apply_edits(str(f), {"inline": {"hidden": '"gated (403)"  # note'}}, warnings)
    out = f.read_text(encoding="utf-8")
    assert n == 1
    assert not warnings
    assert _model_info(out)["inline"] == {"label": "In", "type": "motion", "video_input": True, "hidden": "gated (403)"}


def test_unknown_model_warns_and_skips(tmp_path):
    out, n, warns = _write_apply(tmp_path, {"missing": {"hidden": audit._REMOVE}})
    assert n == 0
    assert warns
    assert out == SAMPLE
