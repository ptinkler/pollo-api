"""Tests for web.venice_chat — Venice text, image and video models in chat (no network)."""
import base64
import json

import httpx
import pytest

from tests.test_chat import SETTINGS, _events, _png_bytes, chat, client, conv, db  # noqa: F401

MODELS = {
    "text": [{"id": "llama-big", "context_length": 128000, "created": 1, "model_spec": {
        "name": "Llama Big", "availableContextTokens": 128000,
        "pricing": {"input": {"usd": 1.0}, "output": {"usd": 4.0}},
        "capabilities": {"supportsVision": True, "supportsFunctionCalling": True}}},
        {"id": "venice-uncensored", "model_spec": {"name": "Venice Uncensored", "uncensored": True, "capabilities": {}}}],
    "image": [
        {"id": "seedream-v5-pro", "model_spec": {"name": "Seedream 5 Pro", "pricing": {"generation": {"usd": 0.05}},
                                                 "constraints": {"aspectRatios": ["1:1", "16:9"], "resolutions": ["1K", "2K"]}}},
        {"id": "grok-imagine-image-quality", "model_spec": {"name": "Grok Quality", "constraints": {}}},
        {"id": "lustify-v8", "model_spec": {"name": "Lustify", "uncensored": True, "constraints": {}}},
        {"id": "gone", "model_spec": {"name": "Gone", "offline": True}},
    ],
    "inpaint": [
        {"id": "seedream-v5-pro-edit", "model_spec": {"name": "Seedream Edit", "pricing": {"inpaint": {"usd": 0.06}},
                                                      "constraints": {"maxInputImages": 2}}},
        {"id": "grok-imagine-quality-edit", "model_spec": {"name": "Grok Q Edit", "constraints": {}}},
        {"id": "firered-image-edit", "model_spec": {"name": "FireRed", "constraints": {}}},
        {"id": "qwen-edit-uncensored", "model_spec": {"name": "Qwen Edit", "uncensored": True, "constraints": {}}},
    ],
    "video": [
        {"id": "wan-3-0-text-to-video", "model_spec": {"name": "Wan 3.0", "constraints": {
            "model_type": "text-to-video", "durations": ["2s", "5s", "10s"], "resolutions": ["720p", "1080p"],
            "aspect_ratios": ["16:9", "9:16"], "audio": True, "audio_configurable": True}}},
        {"id": "wan-3-0-image-to-video", "model_spec": {"name": "Wan 3.0 I2V", "constraints": {
            "model_type": "image-to-video", "durations": ["5s", "10s"], "resolutions": ["720p"],
            "aspect_ratios": [], "audio": True, "audio_configurable": True}}},
        {"id": "wan-3-0-reference-to-video", "model_spec": {"name": "Wan Ref", "constraints": {
            "model_type": "image-to-video", "durations": ["5s"]}}},
        {"id": "flux-3-first-last-frame-to-video", "model_spec": {"name": "Flux 3 FLF", "constraints": {
            "model_type": "image-to-video", "durations": ["5s", "10s"], "resolutions": ["720p"]}}},
        {"id": "wan-2-7-video-to-video", "model_spec": {"name": "Wan 2.7 V2V", "uncensored": True, "constraints": {
            "model_type": "video", "durations": ["Auto"], "resolutions": ["720p"]}}},
        {"id": "topaz-video-upscale", "model_spec": {"name": "Topaz", "constraints": {
            "model_type": "video", "durations": ["Auto"], "resolutions": ["2x", "4x"]}}},
        {"id": "ovi-image-to-video", "model_spec": {"name": "Ovi", "uncensored": True, "constraints": {
            "model_type": "image-to-video", "durations": ["5s"], "audio": True, "audio_configurable": False}}},
    ],
}


QUOTES = {"wan-3-0-text-to-video": 0.65, "ovi-image-to-video": 0.4, "wan-3-0-reference-to-video": 0.3,
          "flux-3-first-last-frame-to-video": 0.9}


class FakeVenice:
    """Stands in for venice_chat._client; records requests, answers from `routes`."""

    def __init__(self):
        self.calls = []
        self.routes = {}

    def _answer(self, method, url, kw):
        path = url.split("/api/v1", 1)[1]
        self.calls.append((method, path, kw.get("json"), kw.get("params")))
        if path == "/models":
            return httpx.Response(200, json={"data": MODELS[kw["params"]["type"]]},
                                  headers={"x-venice-balance-usd": "12.5"})
        handler = self.routes.get(path)
        if handler is None:
            raise AssertionError(f"unexpected Venice call {method} {path}")
        return handler(kw) if callable(handler) else handler

    def request(self, method, url, **kw):
        return self._answer(method, url, kw)

    def stream(self, method, url, **kw):
        resp = self._answer(method, url, kw)

        class Ctx:
            def __enter__(self_inner):
                return resp
            def __exit__(self_inner, *a):
                return False
        return Ctx()


@pytest.fixture()
def venice(chat, monkeypatch, tmp_path):
    import web.venice_chat as v
    monkeypatch.setenv("VENICE_API_KEY", "v-test")
    fake = FakeVenice()
    # Catalogue builds price each video model; tests that queue videos set their own quote
    fake.routes["/video/quote"] = lambda kw: httpx.Response(200, json={"quote": QUOTES.get(kw["json"]["model"])})
    monkeypatch.setattr(v, "_client", fake)
    v._quotes.clear()
    monkeypatch.setattr(v, "_VIDEO_DIR", tmp_path / "venice-videos")
    v._catalogue.update(at=0.0, data=None)
    v._video_quotes.clear()
    v._download_urls.clear()
    v._balance["usd"] = None
    return v, fake


def _calls(fake, path):
    return [c for c in fake.calls if c[1] == path]


class TestCatalogue:
    def test_lists_text_models_with_prices_and_tools(self, venice):
        v, _ = venice
        unc, m = v.list_models("text")   # uncensored first
        assert m["id"] == "venice/llama-big" and m["name"] == "Venice: Llama Big"
        assert m["uncensored"] is None and unc["uncensored"] is True
        assert m["supports_tools"] is True and m["input_modalities"] == ["text", "image"]
        assert m["prompt_price"] == pytest.approx(1e-6) and m["completion_price"] == pytest.approx(4e-6)

    def test_image_models_pair_with_their_edit_twins(self, venice):
        v, _ = venice
        by_id = {m["id"]: m for m in v.list_models("image")}
        assert by_id["venice/seedream-v5-pro"]["input_modalities"] == ["text", "image"]
        assert by_id["venice/grok-imagine-image-quality"]["input_modalities"] == ["text", "image"]  # "-image" dropped
        assert by_id["venice/lustify-v8"]["input_modalities"] == ["text"]
        assert by_id["venice/lustify-v8"]["uncensored"] is True and by_id["venice/seedream-v5-pro"]["uncensored"] is None
        assert by_id["venice/qwen-edit-uncensored"]["uncensored"] is True
        assert "edit only" in by_id["venice/firered-image-edit"]["name"]
        assert "venice/seedream-v5-pro-edit" not in by_id and "venice/gone" not in by_id
        assert not any(k.startswith("_") for m in by_id.values() for k in m)   # internals stay server-side

    def test_video_models_pair_text_and_image_variants(self, venice):
        v, _ = venice
        by_id = {m["id"]: m for m in v.list_models("video")}
        assert set(by_id) == {"venice/wan-3-0-text-to-video", "venice/ovi-image-to-video",
                              "venice/wan-3-0-reference-to-video", "venice/flux-3-first-last-frame-to-video",
                              "venice/wan-2-7-video-to-video", "venice/topaz-video-upscale"}
        assert [by_id[f"venice/{i}"]["family"] for i in ("flux-3-first-last-frame-to-video", "wan-2-7-video-to-video",
                                                          "topaz-video-upscale")] == ["frames", "video", "upscale"]
        assert by_id["venice/flux-3-first-last-frame-to-video"]["frame_images"] == ["first_frame", "last_frame"]
        assert by_id["venice/wan-2-7-video-to-video"]["video_input"] is True
        ids = [m["id"] for m in v.list_models("video")]
        assert all(by_id[i]["uncensored"] for i in ids[:2]) and not any(by_id[i]["uncensored"] for i in ids[2:])   # uncensored first
        assert by_id["venice/wan-3-0-reference-to-video"]["family"] == "reference"
        assert by_id["venice/wan-3-0-reference-to-video"]["reference_images"] is True
        assert "refs→video" in by_id["venice/wan-3-0-reference-to-video"]["name"]
        wan = by_id["venice/wan-3-0-text-to-video"]
        assert wan["frame_images"] == ["first_frame"] and wan["durations"] == [2, 5, 10]
        assert wan["generate_audio"] is True
        assert "image→video only" in by_id["venice/ovi-image-to-video"]["name"]
        assert by_id["venice/ovi-image-to-video"]["uncensored"] is True and wan["uncensored"] is None

    def test_chat_catalogue_includes_venice_alongside_openrouter(self, client, chat, venice, monkeypatch):
        monkeypatch.setattr(chat.openrouter, "list_text_models", lambda: [{"id": "or/text", "name": "OR"}])
        monkeypatch.setattr(chat.openrouter, "list_image_models", lambda: [])
        monkeypatch.setattr(chat.openrouter, "list_video_models", lambda: [])
        data = client.get("/api/chat/models").json()
        assert [m["id"] for m in data["text"]] == ["venice/venice-uncensored", "venice/llama-big", "or/text"]
        assert any(m["id"] == "venice/seedream-v5-pro" for m in data["image"])

    def test_not_listed_without_a_key(self, venice, monkeypatch):
        v, fake = venice
        monkeypatch.delenv("VENICE_API_KEY")
        assert v.list_models("image") == [] and fake.calls == []


class TestPriceOrder:
    def test_privacy_level(self, venice, monkeypatch):
        """A pair is only as private as its less private half."""
        v, _ = venice
        monkeypatch.setitem(MODELS, "image", [
            {"id": "own", "model_spec": {"name": "O", "privacy": "private"}},
            {"id": "mixed", "model_spec": {"name": "M", "privacy": "private"}},
        ])
        monkeypatch.setitem(MODELS, "inpaint", [
            {"id": "mixed-edit", "model_spec": {"name": "ME", "privacy": "anonymized"}},
        ])
        got = {m["id"][7:]: m["privacy"] for m in v.list_models("image")}
        assert got["own"] == "private"
        assert got["mixed"] == "anonymized"

    def test_uncensored_first_then_cheapest(self, venice, monkeypatch):
        v, _ = venice
        monkeypatch.setitem(MODELS, "image", [
            {"id": "pricey-unc", "model_spec": {"name": "B", "uncensored": True, "pricing": {"generation": {"usd": 0.09}}}},
            {"id": "cheap-unc", "model_spec": {"name": "C", "uncensored": True, "pricing": {"generation": {"usd": 0.01}}}},
            {"id": "tiered", "model_spec": {"name": "T", "pricing": {"resolutions": {"1K": {"usd": 0.07}, "2K": {"usd": 0.1}}},
                                            "constraints": {"resolutions": ["1K", "2K"], "defaultResolution": "1K"}}},
            {"id": "cheapest-safe", "model_spec": {"name": "S", "pricing": {"generation": {"usd": 0.005}}}},
            {"id": "unpriced", "model_spec": {"name": "U"}},
        ])
        mine = {"pricey-unc", "cheap-unc", "tiered", "cheapest-safe", "unpriced"}
        models = [m for m in v.list_models("image") if m["id"][7:] in mine]   # edit-only fixtures left out
        assert [m["id"][7:] for m in models] == ["cheap-unc", "pricey-unc", "cheapest-safe", "tiered", "unpriced"]
        assert models[3]["price"] == {"usd": 0.07, "basis": "1K"}

    def test_tiered_image_is_billed_at_the_resolution_used(self, venice, monkeypatch):
        v, fake = venice
        monkeypatch.setitem(MODELS, "image", [
            {"id": "tiered", "model_spec": {"name": "T", "pricing": {"resolutions": {"1K": {"usd": 0.07}, "2K": {"usd": 0.1}}},
                                            "constraints": {"resolutions": ["1K", "2K"], "defaultResolution": "1K"}}}])
        fake.routes["/image/generate"] = httpx.Response(200, json={"images": [base64.b64encode(_png_bytes()).decode()]})
        assert v.generate_image("venice/tiered", "x", resolution="2K")[1] == 0.1
        assert v.generate_image("venice/tiered", "x")[1] == 0.07

    def test_videos_priced_at_5s_lowest_resolution_and_sorted(self, venice):
        v, fake = venice
        by_id = {m["id"][7:]: m for m in v.list_models("video")}
        assert by_id["wan-3-0-text-to-video"]["price"] == {"usd": 0.65, "basis": "5s · 720p"}
        wan_quote = next(c[2] for c in _calls(fake, "/video/quote") if c[2]["model"] == "wan-3-0-text-to-video")
        assert wan_quote == {"model": "wan-3-0-text-to-video", "duration": "5s", "resolution": "720p"}
        assert by_id["wan-2-7-video-to-video"]["price"] is None          # depends on the source video
        ids = [m["id"][7:] for m in v.list_models("video")]
        assert ids.index("ovi-image-to-video") < ids.index("wan-2-7-video-to-video")   # both uncensored: priced first
        assert ids.index("wan-3-0-reference-to-video") < ids.index("wan-3-0-text-to-video")   # 0.30 < 0.65

    def test_quotes_are_cached_across_catalogue_refreshes(self, venice):
        v, fake = venice
        v.list_models("video")
        n = len(_calls(fake, "/video/quote"))
        v.list_models("video", refresh=True)
        assert len(_calls(fake, "/video/quote")) == n


class TestImages:
    def test_text_to_image_sends_safe_mode_off(self, venice, tmp_path):
        v, fake = venice
        fake.routes["/image/generate"] = httpx.Response(200, json={"images": [base64.b64encode(_png_bytes()).decode()]})
        images, cost, sent = v.generate_image("venice/seedream-v5-pro", "a fox", aspect_ratio="16:9", resolution="4K")
        body = _calls(fake, "/image/generate")[0][2]
        assert body["model"] == "seedream-v5-pro" and body["safe_mode"] is False and body["hide_watermark"] is True
        assert body["aspect_ratio"] == "16:9" and "resolution" not in body          # 4K isn't offered
        assert images == [(_png_bytes(), "image/png")] and cost == 0.05
        assert sent == {"aspect_ratio": "16:9", "resolution": None}

    def test_references_go_to_the_edit_twin_capped_at_its_limit(self, venice, tmp_path):
        v, fake = venice
        refs = []
        for i in range(3):
            p = tmp_path / f"r{i}.png"
            p.write_bytes(_png_bytes())
            refs.append(p)
        fake.routes["/image/multi-edit"] = httpx.Response(200, content=b"IMG", headers={"content-type": "image/webp"})
        images, cost, sent = v.generate_image("venice/seedream-v5-pro", "same fox, at night", ref_paths=refs)
        body = _calls(fake, "/image/multi-edit")[0][2]
        assert body["modelId"] == "seedream-v5-pro-edit" and body["safe_mode"] is False
        assert len(body["images"]) == 2 and body["images"][0].startswith("data:image/png;base64,")
        assert images == [(b"IMG", "image/webp")] and cost == 0.06 and sent["refs_used"] == 2

    def test_edit_only_model_needs_a_reference(self, venice):
        v, _ = venice
        with pytest.raises(v.VeniceError, match="only edits images"):
            v.generate_image("venice/firered-image-edit", "a fox")

    def test_errors_carry_venices_message(self, venice):
        v, fake = venice
        fake.routes["/image/generate"] = httpx.Response(400, json={"error": "Prompt too long"})
        with pytest.raises(v.VeniceError, match="Venice: Prompt too long"):
            v.generate_image("venice/lustify-v8", "x" * 10)

    def test_chat_image_mode_runs_on_venice(self, client, conv, chat, venice, monkeypatch):
        v, fake = venice
        fake.routes["/image/generate"] = httpx.Response(200, json={"images": [base64.b64encode(_png_bytes()).decode()]})
        monkeypatch.setattr(chat.openrouter, "generate_image", lambda *a, **k: pytest.fail("not OpenRouter"))
        ev = _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={
            "content": "a fox", **SETTINGS, "mode": "image", "image_model": "venice/seedream-v5-pro"}))
        item = ev[-1]["message"]["media"][0]
        assert item["status"] == "done" and item["cost"] == 0.05


    def test_content_violation_flag_is_a_moderation_block(self, venice):
        v, fake = venice
        fake.routes["/image/generate"] = httpx.Response(
            200, json={"images": [base64.b64encode(_png_bytes()).decode()]},
            headers={"x-venice-is-content-violation": "true"})
        with pytest.raises(v.VeniceError, match="content filter") as e:
            v.generate_image("venice/seedream-v5-pro", "a fox")
        assert e.value.status == 403

    def test_black_image_fails_as_moderated(self, client, conv, chat, venice):
        """Provider filters send a solid black image instead of an error."""
        v, fake = venice
        black = base64.b64encode(_png_bytes(color="black")).decode()
        fake.routes["/image/generate"] = httpx.Response(200, json={"images": [black]})
        ev = _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={
            "content": "a fox", **SETTINGS, "mode": "image", "image_model": "venice/seedream-v5-pro"}))
        item = ev[-1]["message"]["media"][0]
        assert item["status"] == "error" and item["moderated"] is True
        assert "black image" in item["error"]

    def test_dark_but_not_black_image_is_kept(self, client, conv, chat, venice):
        v, fake = venice
        night = base64.b64encode(_png_bytes(color=(20, 20, 30))).decode()
        fake.routes["/image/generate"] = httpx.Response(200, json={"images": [night]})
        ev = _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={
            "content": "a fox at night", **SETTINGS, "mode": "image", "image_model": "venice/seedream-v5-pro"}))
        assert ev[-1]["message"]["media"][0]["status"] == "done"

class TestVideo:
    def _frame(self, tmp_path):
        p = tmp_path / "frame.png"
        p.write_bytes(_png_bytes())
        return p

    def test_text_to_video_snaps_duration_and_quotes(self, venice):
        v, fake = venice
        fake.routes["/video/quote"] = httpx.Response(200, json={"quote": 0.42})
        fake.routes["/video/queue"] = httpx.Response(200, json={"model": "wan-3-0-text-to-video", "queue_id": "q1"})
        job = v.submit_video("venice/wan-3-0-text-to-video", "waves", duration=7, aspect_ratio="16:9",
                             resolution="1080p", generate_audio=False)
        body = _calls(fake, "/video/queue")[0][2]
        assert body == {"model": "wan-3-0-text-to-video", "prompt": "waves", "duration": "5s",
                        "aspect_ratio": "16:9", "resolution": "1080p", "audio": False}
        assert job["id"] == "venice:wan-3-0-text-to-video:q1"
        assert job["params"] == {"duration": 5, "aspect_ratio": "16:9", "resolution": "1080p", "generate_audio": False}

    def test_first_frame_switches_to_the_image_to_video_twin(self, venice, tmp_path):
        v, fake = venice
        fake.routes["/video/quote"] = httpx.Response(500, json={"error": "quote down"})   # optional
        fake.routes["/video/queue"] = httpx.Response(200, json={"queue_id": "q2"})
        job = v.submit_video("venice/wan-3-0-text-to-video", "she waves", duration=10, aspect_ratio="16:9",
                             resolution="1080p", first_frame=self._frame(tmp_path))
        body = _calls(fake, "/video/queue")[0][2]
        assert body["model"] == "wan-3-0-image-to-video" and body["image_url"].startswith("data:image/png")
        assert "aspect_ratio" not in body and "resolution" not in body and body["duration"] == "10s"
        assert job["id"] == "venice:wan-3-0-image-to-video:q2"

    def test_image_only_model_needs_a_frame(self, venice):
        v, _ = venice
        with pytest.raises(v.VeniceError, match="needs an image"):
            v.submit_video("venice/ovi-image-to-video", "waves")

    def test_poll_then_download(self, venice, tmp_path):
        v, fake = venice
        fake.routes["/video/quote"] = httpx.Response(200, json={"quote": 0.3})
        fake.routes["/video/queue"] = httpx.Response(200, json={"queue_id": "q3"})
        job = v.submit_video("venice/wan-3-0-text-to-video", "waves", duration=5)
        fake.routes["/video/retrieve"] = httpx.Response(200, json={"status": "PROCESSING", "average_execution_time": 1})
        assert v.get_video(job["id"]) == {"status": "in_progress"}
        assert _calls(fake, "/video/retrieve")[0][2] == {"model": "wan-3-0-text-to-video", "queue_id": "q3"}
        fake.routes["/video/retrieve"] = httpx.Response(200, content=b"MP4DATA", headers={"content-type": "video/mp4"})
        assert v.get_video(job["id"]) == {"status": "completed", "usage": {"cost": 0.3}}
        dest = tmp_path / "out" / "vid.mp4"
        v.download_video(job["id"], dest)
        assert dest.read_bytes() == b"MP4DATA"

    def test_failed_job_and_transient_errors(self, venice):
        v, fake = venice
        fake.routes["/video/retrieve"] = httpx.Response(400, json={"error": "Content policy violation"})
        assert v.get_video("venice:m:q") == {"status": "failed", "error": "Venice: Content policy violation"}
        fake.routes["/video/retrieve"] = httpx.Response(503, text="busy")
        with pytest.raises(v.VeniceError):
            v.get_video("venice:m:q")   # the poller retries these


class TestText:
    def _sse(self, *chunks):
        lines = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
        return httpx.Response(200, content=lines.encode(), headers={"content-type": "text/event-stream"})

    def test_streams_without_venices_system_prompt_and_prices_usage(self, venice):
        v, fake = venice
        fake.routes["/chat/completions"] = self._sse(
            {"choices": [{"delta": {"content": "Hi"}}]},
            {"choices": [], "usage": {"prompt_tokens": 1000, "completion_tokens": 500}})
        chunks = list(v.stream_chat("venice/llama-big", [{"role": "user", "content": "hello"}],
                                    tools=[{"type": "function", "function": {"name": "f"}}]))
        body = _calls(fake, "/chat/completions")[0][2]
        assert body["model"] == "llama-big" and body["venice_parameters"] == {"include_venice_system_prompt": False}
        assert body["stream_options"] == {"include_usage": True} and body["tools"][0]["function"]["name"] == "f"
        assert chunks[0]["choices"][0]["delta"]["content"] == "Hi"
        assert chunks[1]["usage"]["cost"] == pytest.approx(1000 * 1e-6 + 500 * 4e-6)

    def test_reported_cost_object_wins(self, venice):
        v, fake = venice
        fake.routes["/chat/completions"] = self._sse(
            {"choices": [], "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": {"usd": 0.0123, "diem": 0}}})
        [chunk] = list(v.stream_chat("venice/llama-big", []))
        assert chunk["usage"]["cost"] == 0.0123

    def test_chat_turn_uses_venice_for_a_venice_text_model(self, client, conv, chat, venice, monkeypatch):
        v, fake = venice
        fake.routes["/chat/completions"] = self._sse({"choices": [{"delta": {"content": "From Venice"}}]})
        monkeypatch.setattr(chat.openrouter, "stream_chat", lambda *a, **k: pytest.fail("not OpenRouter"))
        ev = _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={
            "content": "hi", **SETTINGS, "text_model": "venice/llama-big"}))
        assert ev[-1]["message"]["content"] == "From Venice"


    def test_no_images_for_a_model_without_vision_before_the_model_list_loads(self, client, conv, chat, venice):
        """After a restart (or a failed model list) the app still knows from
        Venice's own catalogue that the model can't see images."""
        v, fake = venice
        fake.routes["/chat/completions"] = self._sse({"choices": [{"delta": {"content": "ok"}}]})
        assert chat._models_cache["data"] is None
        up = client.post(f"/api/chat/conversations/{conv['id']}/attachments",
                         files={"file": ("a.png", _png_bytes(), "image/png")}).json()["file"]
        ev = _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={
            "content": "like this", **SETTINGS, "mode": "auto", "text_model": "venice/venice-uncensored",
            "attachments": [up]}))
        assert ev[-1]["message"]["status"] != "error"
        sent = json.dumps(_calls(fake, "/chat/completions")[0][2]["messages"])
        assert "image_url" not in sent and "[user attached an image]" in sent

def test_balance_falls_back_to_the_response_header(client, venice):
    v, fake = venice
    fake.routes["/billing/balance"] = httpx.Response(401, json={"error": "Admin API key required"})
    fake.routes["/api_keys/rate_limits"] = httpx.Response(200, json={}, headers={"x-venice-balance-usd": "7.25"})
    assert client.get("/api/chat/venice-balance").json() == {"usd": 7.25}


class TestVideoFamiliesInChat:
    """Reference, first+last-frame and video-input models get the right inputs from the chat."""

    def _load_catalogue(self, client, chat, monkeypatch):
        for fn in ("list_text_models", "list_image_models", "list_video_models"):
            monkeypatch.setattr(chat.openrouter, fn, lambda: [])
        client.get("/api/chat/models")

    def _queue(self, fake, queue_id="q"):
        fake.routes["/video/quote"] = httpx.Response(200, json={"quote": 0.1})
        fake.routes["/video/queue"] = httpx.Response(200, json={"queue_id": queue_id})

    def _image(self, chat, conv, name):
        (chat._conv_dir(conv["id"]) / name).write_bytes(_png_bytes())

    def test_reference_model_gets_attached_pinned_and_character_images(self, client, conv, chat, db, venice, monkeypatch):
        v, fake = venice
        self._load_catalogue(client, chat, monkeypatch)
        self._queue(fake)
        for f in ("pin.png", "a.png", "b.png"):
            self._image(chat, conv, f)
        db.add_chat_message(conv["id"], "user", "x")
        msg = db.add_chat_message(conv["id"], "assistant", "", media=[
            {"id": "p", "kind": "image", "source": "generated", "status": "done", "file": "pin.png", "prompt": "p"}])
        client.post(f"/api/chat/messages/{msg.id}/media/p/pin", json={"pinned": True})
        ups = [client.post(f"/api/chat/conversations/{conv['id']}/attachments",
                           files={"file": (n, _png_bytes(), "image/png")}).json()["file"] for n in ("a.png", "b.png")]
        ev = _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={
            "content": "they dance", "attachments": ups, **SETTINGS, "mode": "video",
            "video_model": "venice/wan-3-0-reference-to-video"}))
        body = _calls(fake, "/video/queue")[0][2]
        assert body["model"] == "wan-3-0-reference-to-video" and len(body["reference_image_urls"]) == 3
        item = ev[-1]["message"]["media"][0]
        assert item["params"]["refs"] == [*ups, "pin.png"] and item["params"]["refs_used"] == 3

    def test_first_and_last_frame_from_two_attachments(self, client, conv, chat, venice, monkeypatch):
        v, fake = venice
        self._load_catalogue(client, chat, monkeypatch)
        self._queue(fake)
        ups = [client.post(f"/api/chat/conversations/{conv['id']}/attachments",
                           files={"file": (n, _png_bytes(), "image/png")}).json()["file"] for n in ("s.png", "e.png")]
        ev = _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={
            "content": "morph", "attachments": ups, **SETTINGS, "mode": "video",
            "video_model": "venice/flux-3-first-last-frame-to-video"}))
        body = _calls(fake, "/video/queue")[0][2]
        assert body["image_url"].startswith("data:image") and body["end_image_url"].startswith("data:image")
        assert ev[-1]["message"]["media"][0]["params"]["last_frame"] == ups[1]

    def test_video_to_video_uses_the_latest_chat_video(self, client, conv, chat, db, venice, monkeypatch):
        v, fake = venice
        self._load_catalogue(client, chat, monkeypatch)
        self._queue(fake)
        (chat._conv_dir(conv["id"]) / "vid_old.mp4").write_bytes(b"MP4")
        db.add_chat_message(conv["id"], "user", "x")
        db.add_chat_message(conv["id"], "assistant", "", media=[
            {"id": "v1", "kind": "video", "source": "generated", "status": "done", "file": "vid_old.mp4", "prompt": "p"}])
        ev = _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={
            "content": "make it anime", **SETTINGS, "mode": "video", "video_model": "venice/wan-2-7-video-to-video"}))
        body = _calls(fake, "/video/queue")[0][2]
        assert body["video_url"].startswith("data:") and body["duration"] == "Auto"
        assert ev[-1]["message"]["media"][0]["params"]["source_video"] == "vid_old.mp4"

    def test_upscale_maps_the_resolution_pick_to_a_factor(self, venice, tmp_path):
        v, fake = venice
        self._queue(fake)
        src = tmp_path / "in.mp4"
        src.write_bytes(b"MP4")
        job = v.submit_video("venice/topaz-video-upscale", "", resolution="4x", source_video=src)
        body = _calls(fake, "/video/queue")[0][2]
        assert body["upscale_factor"] == 4 and "resolution" not in body and job["params"]["resolution"] == "4x"

    def test_missing_inputs_explain_what_is_needed(self, venice, tmp_path):
        v, _ = venice
        with pytest.raises(v.VeniceError, match="reference images"):
            v.submit_video("venice/wan-3-0-reference-to-video", "x")
        with pytest.raises(v.VeniceError, match="first and a last frame"):
            v.submit_video("venice/flux-3-first-last-frame-to-video", "x")
        with pytest.raises(v.VeniceError, match="works on a video"):
            v.submit_video("venice/wan-2-7-video-to-video", "x")
