"""Tests for Seedance 2.5 Draft / Extend and Pollo's price checks (web.pollo_estimate)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from img2vid.pollo.generators import (
    Seedance25DraftVideoGenerator,
    Seedance25DraftVideoGeneratorV1,
    Seedance25ExtendVideoGeneratorV1,
    Seedance25VideoGeneratorV1,
)
from web import pollo_estimate

V1 = "https://pollo.ai/api/platform/v1/generation"
LEGACY = "https://pollo.ai/api/platform/generation"


@pytest.fixture(autouse=True)
def _no_project_files():
    with (
        patch("img2vid.pollo.generators.get_prompt", return_value="p"),
        patch("img2vid.pollo.generators.get_image_url", return_value=None),
        patch("img2vid.pollo.generators.get_image_path", return_value=None),
        patch("img2vid.pollo.generators.get_video_url", return_value=None),
    ):
        yield
    pollo_estimate.clear_cache()


def _response(status: int, body) -> MagicMock:
    resp = MagicMock(status_code=status, text=str(body), headers={})
    resp.json.return_value = body
    return resp


class TestSeedance25Draft:
    def test_v1_is_480p_only_without_web_search(self):
        gen = Seedance25DraftVideoGeneratorV1(api_key="k", project="p", prompt="x", resolution="720p", web_search=True)
        assert gen.model_url == f"{V1}/bytedance/seedance-2-5-draft/video"
        payload = gen.get_payload()["input"]
        assert payload["resolution"] == "480p"
        assert "webSearch" not in payload
        assert payload["aspectRatio"] == "adaptive"

    def test_v1_keeps_end_frame_and_refs(self):
        gen = Seedance25DraftVideoGeneratorV1(
            api_key="k", project="p", prompt="x", image_url="https://i/a.png", image_tail="https://i/b.png"
        )
        assert gen.get_payload()["input"]["imageTail"] == "https://i/b.png"
        assert Seedance25DraftVideoGeneratorV1.MAX_REFS == Seedance25VideoGeneratorV1.MAX_REFS

    def test_legacy(self):
        gen = Seedance25DraftVideoGenerator(api_key="k", project="p", prompt="x", resolution="720p")
        assert gen.model_url == f"{LEGACY}/bytedance/seedance-2-5-draft"
        assert gen.get_payload()["input"]["resolution"] == "480p"


class TestSeedance25Extend:
    def test_payload(self):
        gen = Seedance25ExtendVideoGeneratorV1(
            api_key="k",
            project="p",
            prompt="keep walking",
            video_url="https://v/a.mp4",
            length=8,
            resolution="720p",
            generate_audio=False,
            seed=7,
            aspect_ratio="16:9",
        )
        assert gen.model_url == f"{V1}/bytedance/seedance-2-5/video-extend"
        assert gen.is_video_edit and not gen.is_text_only
        assert gen.get_payload() == {
            "input": {
                "video": "https://v/a.mp4",
                "prompt": "keep walking",
                "duration": 8,
                "resolution": "720p",
                "generateAudio": False,
                "seed": 7,
            }
        }

    def test_no_source_image_and_prompt_optional(self):
        with patch("img2vid.pollo.generators.get_image_url", return_value="https://i/project.png"):
            gen = Seedance25ExtendVideoGeneratorV1(api_key="k", project="p", prompt="", video_url="https://v/a.mp4")
        assert gen.image_url is None
        gen.prompt = ""
        assert "prompt" not in gen.get_payload()["input"]

    def test_needs_a_video(self):
        gen = Seedance25ExtendVideoGeneratorV1(api_key="k", project="p", prompt="x")
        with pytest.raises(ValueError, match="source video"):
            gen.get_payload()


class TestEstimateUrl:
    def test_v1_and_legacy(self):
        v1 = Seedance25DraftVideoGeneratorV1(api_key="k", project="p", prompt="x")
        assert v1.estimate_url == f"{V1}/bytedance/seedance-2-5-draft/video/estimate"
        extend = Seedance25ExtendVideoGeneratorV1(api_key="k", project="p", prompt="x", video_url="https://v")
        assert extend.estimate_url == f"{V1}/bytedance/seedance-2-5/video-extend/estimate"
        legacy = Seedance25DraftVideoGenerator(api_key="k", project="p", prompt="x")
        assert legacy.estimate_url == f"{LEGACY}/bytedance/seedance-2-5-draft/validate"

    def test_legacy_ref2video_has_none(self):
        from img2vid.pollo.generators import SeedanceRefVideoGenerator

        gen = SeedanceRefVideoGenerator(api_key="k", project="p", prompt="x", refs=[])
        assert gen.estimate_url is None


class TestEstimate:
    def _gen(self, **kw):
        return Seedance25DraftVideoGeneratorV1(api_key="k", project="p", prompt="x", **kw)

    @patch("web.pollo_estimate.requests.post")
    def test_v1_answer(self, post):
        post.return_value = _response(200, {"code": "SUCCESS", "data": {"cost": 40, "discountCost": 30.0}})
        assert pollo_estimate.estimate(self._gen()) == {"credits": 30, "full_credits": 40}
        url, kwargs = post.call_args.args[0], post.call_args.kwargs
        assert url.endswith("/seedance-2-5-draft/video/estimate")
        assert kwargs["headers"]["x-api-key"] == "k"
        assert kwargs["json"]["input"]["resolution"] == "480p"

    @patch("web.pollo_estimate.requests.post")
    def test_legacy_answer_unwrapped(self, post):
        post.return_value = _response(200, {"cost": 10, "totalCost": 20})
        assert pollo_estimate.estimate(self._gen()) == {"credits": 20, "full_credits": 20}

    @patch("web.pollo_estimate.requests.post")
    def test_cached_per_request(self, post):
        post.return_value = _response(200, {"data": {"cost": 12}})
        assert pollo_estimate.estimate(self._gen(length=5))["credits"] == 12
        assert pollo_estimate.estimate(self._gen(length=5))["credits"] == 12
        assert post.call_count == 1
        pollo_estimate.estimate(self._gen(length=6))
        assert post.call_count == 2

    @patch("web.pollo_estimate.requests.post")
    def test_refusal_is_cached(self, post):
        post.return_value = _response(404, {"message": "Not found"})
        assert pollo_estimate.estimate(self._gen()) is None
        assert pollo_estimate.estimate(self._gen()) is None
        assert post.call_count == 1

    @patch("web.pollo_estimate.requests.post")
    def test_outages_are_not_cached(self, post):
        post.side_effect = requests.ConnectionError("down")
        assert pollo_estimate.estimate(self._gen()) is None
        post.side_effect = None
        post.return_value = _response(502, "bad gateway")
        assert pollo_estimate.estimate(self._gen()) is None
        post.return_value = _response(200, {"data": {"cost": 5}})
        assert pollo_estimate.estimate(self._gen())["credits"] == 5
        assert post.call_count == 3

    @patch("web.pollo_estimate.requests.post")
    def test_answer_without_a_price(self, post):
        post.return_value = _response(200, {"data": {"something": "else"}})
        assert pollo_estimate.estimate(self._gen()) is None


# ── The API ──────────────────────────────────────────────────────────


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import web.api as api_mod
    from img2vid.common.metadata import MetadataDB

    monkeypatch.setenv("POLLO_API_KEY", "test-key")
    (tmp_path / "data").mkdir(exist_ok=True)
    db = MetadataDB(db_path=tmp_path / "data" / "metadata.db")
    monkeypatch.setattr(api_mod, "ASSETS_DIR", tmp_path / "assets")
    monkeypatch.setattr(api_mod, "get_db", lambda: db)
    import web.characters as characters_mod

    monkeypatch.setattr(characters_mod, "get_db", lambda: db)
    api_mod._project_lookup_cache.clear()
    from fastapi.testclient import TestClient

    c = TestClient(api_mod.app, raise_server_exceptions=False)
    c.db = db
    return c


class TestEstimateEndpoint:
    @patch("web.pollo_estimate.requests.post")
    def test_asks_pollo_with_placeholders(self, post, client):
        post.return_value = _response(200, {"data": {"cost": 25, "discountCost": 20}})
        resp = client.post(
            "/api/usage/estimate",
            json={"model": "seedance25draftv1", "image": True, "image_tail": True, "length": 6, "generate_audio": True},
        )
        assert resp.status_code == 200
        assert resp.json() == {"credits": 20, "full_credits": 25, "samples": None, "source": "pollo"}
        body = post.call_args.kwargs["json"]["input"]
        assert body["image"] == pollo_estimate.PLACEHOLDERS["image"]
        assert body["imageTail"] == pollo_estimate.PLACEHOLDERS["image"]
        assert body["duration"] == 6 and body["prompt"] == "estimate"

    @patch("web.pollo_estimate.requests.post")
    def test_refs_and_extend(self, post, client):
        post.return_value = _response(200, {"data": {"cost": 9}})
        client.post("/api/usage/estimate", json={"model": "seedance25v1", "ref_types": ["image", "video"]})
        refs = post.call_args.kwargs["json"]["input"]["refs"]
        assert [r["type"] for r in refs] == ["image", "video"]
        assert refs[1]["url"] == pollo_estimate.PLACEHOLDERS["video"]
        video = "https://videocdn.pollo.ai/a.mp4"
        client.post("/api/usage/estimate", json={"model": "seedance25extendv1", "length": 10, "video_url": video})
        assert post.call_args.args[0].endswith("/seedance-2-5/video-extend/estimate")
        assert post.call_args.kwargs["json"]["input"]["video"] == video

    @patch("web.pollo_estimate.requests.post")
    def test_extend_of_a_project_only_video_isnt_asked(self, post, client):
        resp = client.post("/api/usage/estimate", json={"model": "seedance25extendv1", "video_url": "local:v.mp4"})
        assert resp.json()["source"] is None
        post.assert_not_called()

    @patch("web.pollo_estimate.requests.post")
    def test_image_models(self, post, client):
        post.return_value = _response(200, {"data": {"cost": 1}})
        resp = client.post("/api/usage/estimate", json={"model": "nanobanana2v1", "image": True, "resolution": "2K"})
        assert resp.json()["credits"] == 1
        assert post.call_args.args[0].endswith("/google/nano-banana-2/image/estimate")
        assert post.call_args.kwargs["json"]["input"]["images"] == [pollo_estimate.PLACEHOLDERS["image"]]

    @patch("web.pollo_estimate.requests.post")
    def test_falls_back_to_past_jobs(self, post, client):
        post.return_value = _response(403, {"message": "not enabled"})
        db = client.db
        proj = db.create_project(name="E")
        for i in range(2):
            db.create_job(
                job_id=f"e{i}", project=proj.slug, model="seedance25draftv1", prompt="p", resolution="480p", length=5
            )
            db.update_job(f"e{i}", credits_used=15)
        resp = client.post(
            "/api/usage/estimate", json={"model": "seedance25draftv1", "resolution": "480p", "length": 5}
        )
        assert resp.json() == {"credits": 15, "full_credits": 15, "samples": 2, "source": "history"}

    def test_nothing_known(self, client, monkeypatch):
        monkeypatch.delenv("POLLO_API_KEY")
        resp = client.post("/api/usage/estimate", json={"model": "seedance25v1"})
        assert resp.json() == {"credits": None, "full_credits": None, "samples": 0, "source": None}

    def test_unknown_model(self, client):
        assert client.post("/api/usage/estimate", json={"model": "nope"}).status_code == 400


class TestExtendGenerate:
    def _project(self, client):
        import web.api as api_mod

        proj = client.db.create_project(name="X")
        folder = api_mod.ASSETS_DIR / proj.assets_folder
        folder.mkdir(parents=True, exist_ok=True)
        return proj, folder

    def test_needs_a_video(self, client):
        proj, _ = self._project(client)
        resp = client.post("/api/generate", json={"model": "seedance25extendv1", "project": proj.slug, "prompt": "x"})
        assert resp.status_code == 400
        assert "video" in resp.json()["detail"]

    @patch("web.api.threading.Thread")
    def test_pollo_url_without_prompt(self, thread, client):
        proj, _ = self._project(client)
        resp = client.post(
            "/api/generate",
            json={
                "model": "seedance25extendv1",
                "project": proj.slug,
                "prompt": "",
                "video_url": "https://videocdn.pollo.ai/a.mp4",
                "image_url": "https://i/ignored.png",
                "seed": 3,
                "web_search": True,
            },
        )
        assert resp.status_code == 200
        kwargs = thread.call_args.kwargs["args"][2]
        assert kwargs["video_url"] == "https://videocdn.pollo.ai/a.mp4"
        assert kwargs["image_url"] is None
        assert kwargs["seed"] == 3 and "web_search" not in kwargs
        job = client.db.get_job(resp.json()["job_id"])
        assert job.source_video_url == "https://videocdn.pollo.ai/a.mp4"

    @patch("web.api.threading.Thread")
    @patch("web.api.image_hosts.upload_image", return_value="https://tmpfiles.org/dl/1/v.mp4")
    def test_local_video_is_uploaded(self, upload, thread, client):
        proj, folder = self._project(client)
        (folder / "v.mp4").write_bytes(b"video")
        resp = client.post(
            "/api/generate",
            json={"model": "seedance25extendv1", "project": proj.slug, "prompt": "on", "video_url": "local:v.mp4"},
        )
        assert resp.status_code == 200
        assert Path(upload.call_args.args[0]).name == "v.mp4"
        assert thread.call_args.kwargs["args"][2]["video_url"] == "https://tmpfiles.org/dl/1/v.mp4"

    def test_rejects_other_addresses(self, client):
        proj, _ = self._project(client)
        resp = client.post(
            "/api/generate",
            json={"model": "seedance25extendv1", "project": proj.slug, "prompt": "x", "video_url": "file:///etc/x"},
        )
        assert resp.status_code == 400


def test_chat_doesnt_offer_extend(monkeypatch):
    from web import pollo_chat

    monkeypatch.setattr(pollo_chat, "is_configured", lambda: True)
    ids = {m["id"] for m in pollo_chat.list_video_models()}
    assert "pollo/seedance25draftv1" in ids
    assert "pollo/seedance25extendv1" not in ids
