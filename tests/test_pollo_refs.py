"""Reference-to-video (refs branch): the named refs list a ref_mode model gets,
how attachments map to [@name] handles with per-type caps, and the submit path
that uploads each ref and routes to Pollo's reference-to-video branch."""

import types
from pathlib import Path

import pytest

import web.providers.pollo as pollo
from web.chat.turn import Turn

pytestmark = pytest.mark.no_tenant


def _user(*media):
    """A user message whose media is (kind, file) pairs, in order."""
    return types.SimpleNamespace(media=[{"kind": k, "file": f} for k, f in media])


class TestRefItems:
    """Turn._ref_items only touches self._last_user(), so a stub drives it."""

    def _items(self, ref_mode, user):
        stub = types.SimpleNamespace(_last_user=lambda: user)
        return Turn._ref_items(stub, ref_mode)

    def test_names_by_type_and_order(self):
        rm = {"types": ["image", "video", "audio"], "max": 15}
        items = self._items(rm, _user(("video", "v1.mp4"), ("image", "a.png"), ("image", "b.png")))
        assert items == [
            {"file": "v1.mp4", "name": "video1", "type": "video"},
            {"file": "a.png", "name": "image1", "type": "image"},
            {"file": "b.png", "name": "image2", "type": "image"},
        ]

    def test_per_type_cap_drops_overflow(self):
        # Kling 3.0 Omni: at most 1 video, 4 images.
        rm = {"types": ["image", "video"], "max": 7, "limits": {"image": 4, "video": 1}}
        items = self._items(rm, _user(("video", "v1.mp4"), ("video", "v2.mp4"), ("image", "a.png")))
        names = [i["name"] for i in items]
        assert "video1" in names and "video2" not in names  # 2nd video over the cap
        assert "image1" in names

    def test_disallowed_type_excluded(self):
        # Flash takes no audio refs.
        rm = {"types": ["image", "video"], "max": 15}
        items = self._items(rm, _user(("audio", "a.mp3"), ("image", "i.png")))
        assert [i["type"] for i in items] == ["image"]

    def test_total_max_caps_list(self):
        rm = {"types": ["image"], "max": 2}
        items = self._items(rm, _user(("image", "a.png"), ("image", "b.png"), ("image", "c.png")))
        assert len(items) == 2


class TestSubmitRefBranch:
    def test_ref_items_route_to_refs_branch(self, monkeypatch, provider_keys):
        provider_keys["pollo"] = "K"
        monkeypatch.setattr(
            pollo,
            "_upload",
            lambda p, what="image": f"https://h/{'vid' if what == 'video' else 'img'}/{Path(p).name}",
        )
        captured = {}

        def fake_submit(gen):
            captured["p"] = gen.get_payload()
            return "task1"

        monkeypatch.setattr(pollo, "_submit", fake_submit)
        job = pollo.submit_video(
            "pollo/klingv4",
            "replace [@video1] with [@image1]",
            duration=5,
            ref_items=[
                {"path": Path("/x/v.mp4"), "name": "video1", "type": "video"},
                {"path": Path("/x/i.png"), "name": "image1", "type": "image"},
            ],
        )
        assert job["id"] == "pollo:task1"
        refs = captured["p"]["input"]["refs"]
        assert [r["name"] for r in refs] == ["video1", "image1"]
        assert refs[0]["url"].startswith("https://h/vid/") and refs[1]["url"].startswith("https://h/img/")
        assert "image" not in captured["p"]["input"]  # refs branch, not image-to-video

    def test_empty_ref_items_use_normal_branch(self, monkeypatch, provider_keys):
        # No refs -> falls through to the plain image/text path (first_frame).
        provider_keys["pollo"] = "K"
        monkeypatch.setattr(pollo, "_submit", lambda gen: gen.get_payload() and "task2")
        job = pollo.submit_video("pollo/klingv4", "a fox runs", duration=5, ref_items=[])
        assert job["id"] == "pollo:task2"


def test_list_video_models_surfaces_ref_mode(provider_keys):
    provider_keys["pollo"] = "K"
    by_id = {m["id"]: m for m in pollo.list_video_models()}
    assert by_id["pollo/klingv4"]["ref_mode"]["limits"] == {"image": 10, "video": 5, "audio": 3}
    assert by_id["pollo/klingv4flash"]["ref_mode"]["types"] == ["image", "video"]
    # A non-refs model carries ref_mode: None.
    assert by_id["pollo/klingv3turbo"]["ref_mode"] is None
