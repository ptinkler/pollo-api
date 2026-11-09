"""Capability tags: the uniform derivation (model_tags.tags_for) and that the
catalogue attaches them to every model it assembles."""

import pytest

from web.chat import catalogue
from web.providers.model_tags import tags_for

pytestmark = pytest.mark.no_tenant


class TestVideoTags:
    def test_pollo_img2vid_with_audio_and_tail(self):
        m = {"type": "img2vid", "generate_audio": True, "frame_images": ["first_frame", "last_frame"]}
        assert tags_for("video", m) == ["img2vid", "text2vid", "first_last", "audio"]

    def test_pollo_motion_models_are_all_recast(self):
        # the first_frame is a reference image, not "animate this image"
        m = {"type": "motion", "frame_images": ["first_frame"]}
        assert tags_for("video", m) == ["motion", "recast"]

    def test_pollo_ref_and_extend(self):
        assert tags_for("video", {"type": "ref"}) == ["ref2vid"]
        assert tags_for("video", {"type": "extend"}) == ["video_extend"]

    def test_pollo_video_edit(self):
        assert tags_for("video", {"type": "video_edit", "frame_images": []}) == ["video_edit"]

    def test_pollo_upscale(self):
        assert tags_for("video", {"type": "upscale", "frame_images": []}) == ["upscale"]

    def test_pollo_lipsync(self):
        # lip sync: the first_frame is the portrait, driven by audio — not img2vid
        assert tags_for("video", {"type": "lipsync", "frame_images": ["first_frame"]}) == ["lipsync"]

    def test_pollo_video_tools(self):
        for typ, tag in (("bgremove", "bg_remove"), ("subtitle_remove", "subtitle_remove"), ("faceswap", "face_swap")):
            assert tags_for("video", {"type": typ, "frame_images": ["first_frame"]}) == [tag]

    def test_image_tool(self):
        assert tags_for("image", {"tool": "upscale"}) == ["tools"]

    def test_pollo_audio(self):
        assert tags_for("audio", {"type": "speech"}) == ["tts"]
        assert tags_for("audio", {"type": "music"}) == ["music"]

    def test_venice_families(self):
        assert tags_for("video", {"family": "motion"}) == ["motion"]
        assert tags_for("video", {"family": "upscale"}) == ["upscale"]
        assert tags_for("video", {"family": "reference", "reference_images": True}) == ["ref2vid"]
        assert tags_for("video", {"family": "frames", "frame_images": ["first_frame", "last_frame"]}) == [
            "img2vid",
            "first_last",
        ]

    def test_venice_standard_text_and_image(self):
        assert tags_for("video", {"family": "standard", "frame_images": ["first_frame"]}) == ["text2vid", "img2vid"]

    def test_openrouter_video_infers_from_modalities(self):
        assert tags_for("video", {"input_modalities": ["text", "image"]}) == ["img2vid", "text2vid"]
        assert tags_for("video", {"input_modalities": ["text"]}) == ["text2vid"]


class TestImageAndTextTags:
    def test_image_edit_vs_text_only(self):
        assert tags_for("image", {"input_modalities": ["text", "image"]}) == ["text2img", "image_edit"]
        assert tags_for("image", {"input_modalities": ["text"], "conversational": True}) == ["text2img", "image_edit"]
        assert tags_for("image", {"input_modalities": ["text"]}) == ["text2img"]

    def test_image_tools(self):
        assert tags_for("image", {"tool": "faceSwap"}) == ["tools"]

    def test_text_vision_and_functions(self):
        assert tags_for("text", {"input_modalities": ["text", "image"], "supports_tools": True}) == [
            "vision",
            "functions",
        ]
        assert tags_for("text", {"input_modalities": ["text"]}) == []


def test_catalogue_attaches_tags_to_every_model(monkeypatch):
    """get_models() tags each model, regardless of which provider produced it."""

    class FakeProvider:
        NAME = "fake"

        def list_models(self, kind, refresh=False):
            if kind == "video":
                return [{"id": "fake/v", "name": "V", "type": "img2vid", "generate_audio": True}]
            if kind == "image":
                return [{"id": "fake/i", "name": "I", "input_modalities": ["text", "image"]}]
            return [{"id": "fake/t", "name": "T", "input_modalities": ["text"], "supports_tools": True}]

    monkeypatch.setattr(catalogue, "PROVIDERS", (FakeProvider(),))
    try:
        data = catalogue.get_models(refresh=True)
        assert data["video"][0]["tags"] == ["img2vid", "text2vid", "audio"]
        assert data["image"][0]["tags"] == ["text2img", "image_edit"]
        assert data["text"][0]["tags"] == ["functions"]
    finally:
        # get_models() caches module-side; drop the fake data so it can't leak
        catalogue._models_cache.update(at=0.0, data=None)
