"""Tests for img2vid.pollo.generators — all video generator classes."""
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from img2vid.pollo.generators import (
    BaseVideoGenerator, Pollo20VideoGenerator,
    PolloDance20VideoGenerator, PolloDance20FastVideoGenerator,
    PolloDanceRefVideoGenerator, PolloDanceRefFastVideoGenerator,
    _parse_bool_env, SUCCESS_STATUSES, ERROR_STATUSES,
)


# ── Constants ────────────────────────────────────────────────────────

class TestConstants:
    def test_success_statuses(self):
        assert "succeed" in SUCCESS_STATUSES
        assert "success" in SUCCESS_STATUSES
        assert "completed" in SUCCESS_STATUSES

    def test_error_statuses(self):
        assert "error" in ERROR_STATUSES
        assert "failed" in ERROR_STATUSES


# ── parse_bool_env ───────────────────────────────────────────────────

class TestParseBoolEnv:
    def test_true_values(self, monkeypatch):
        for val in ("1", "true", "True", "TRUE", "yes", "Yes"):
            monkeypatch.setenv("TEST_BOOL", val)
            assert _parse_bool_env("TEST_BOOL") is True

    def test_false_values(self, monkeypatch):
        for val in ("0", "false", "no", ""):
            monkeypatch.setenv("TEST_BOOL", val)
            assert _parse_bool_env("TEST_BOOL") is False

    def test_missing_env_uses_default(self, monkeypatch):
        monkeypatch.delenv("TEST_BOOL", raising=False)
        assert _parse_bool_env("TEST_BOOL", default=False) is False
        assert _parse_bool_env("TEST_BOOL", default=True) is True


# ── BaseVideoGenerator ──────────────────────────────────────────────

class TestBaseVideoGenerator:
    def test_get_aspect_ratio_portrait(self):
        assert BaseVideoGenerator.get_aspect_ratio("portrait") == "9:16"

    def test_get_aspect_ratio_landscape(self):
        assert BaseVideoGenerator.get_aspect_ratio("landscape") == "16:9"

    def test_get_aspect_ratio_direct(self):
        assert BaseVideoGenerator.get_aspect_ratio("4:3") == "4:3"

    def test_get_aspect_ratio_invalid(self):
        assert BaseVideoGenerator.get_aspect_ratio("invalid") == "9:16"


    def test_get_closest_aspect_ratio(self):
        valid = ("9:16", "16:9", "1:1")
        # 1920x1080 -> 16:9
        result = BaseVideoGenerator.get_closest_aspect_ratio(1920, 1080, valid)
        assert result == "16:9"

    def test_get_closest_aspect_ratio_square(self):
        valid = ("9:16", "16:9", "1:1")
        result = BaseVideoGenerator.get_closest_aspect_ratio(500, 500, valid)
        assert result == "1:1"

    def test_get_closest_aspect_ratio_portrait(self):
        valid = ("9:16", "16:9", "1:1")
        result = BaseVideoGenerator.get_closest_aspect_ratio(1080, 1920, valid)
        assert result == "9:16"

    @patch("img2vid.pollo.generators.get_prompt", return_value="test prompt")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_init_with_kwargs(self, mock_path, mock_url, mock_prompt, monkeypatch):
        monkeypatch.setenv("POLLO_API_KEY", "test-key")
        gen = Pollo20VideoGenerator(api_key="k", project="p", prompt="hello", image_url="https://img.com/i.jpg")
        assert gen.api_key == "k"
        assert gen.project == "p"
        assert gen.prompt == "hello"
        assert gen.image_url == "https://img.com/i.jpg"

    @patch("img2vid.pollo.generators.get_prompt", return_value="test prompt")
    @patch("img2vid.pollo.generators.get_image_url", return_value="https://fallback.com/i.jpg")
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_init_fallback_to_env(self, mock_path, mock_url, mock_prompt, monkeypatch):
        monkeypatch.setenv("POLLO_API_KEY", "env-key")
        monkeypatch.setenv("PROJECT", "envproj")
        gen = Pollo20VideoGenerator()
        assert gen.api_key == "env-key"
        assert gen.project == "envproj"
        assert gen.image_url == "https://fallback.com/i.jpg"

    def test_is_text_only(self):
        with patch("img2vid.pollo.generators.get_prompt", return_value="p"), \
             patch("img2vid.pollo.generators.get_image_url", return_value=None), \
             patch("img2vid.pollo.generators.get_image_path", return_value=None):
            gen = Pollo20VideoGenerator(api_key="k", project="p", prompt="x", image_url=None)
        assert gen.is_text_only is True

    def test_not_text_only(self):
        with patch("img2vid.pollo.generators.get_prompt", return_value="p"), \
             patch("img2vid.pollo.generators.get_image_url", return_value=None), \
             patch("img2vid.pollo.generators.get_image_path", return_value=None):
            gen = Pollo20VideoGenerator(api_key="k", project="p", prompt="x", image_url="https://img.com/i.jpg")
        assert gen.is_text_only is False

    def test_get_payload_not_implemented(self):
        with patch("img2vid.pollo.generators.get_prompt", return_value="p"), \
             patch("img2vid.pollo.generators.get_image_url", return_value=None), \
             patch("img2vid.pollo.generators.get_image_path", return_value=None):
            gen = BaseVideoGenerator(api_key="k", project="p", prompt="x")
        with pytest.raises(NotImplementedError):
            gen.get_payload()

    def test_send_request_no_url(self):
        with patch("img2vid.pollo.generators.get_prompt", return_value="p"), \
             patch("img2vid.pollo.generators.get_image_url", return_value=None), \
             patch("img2vid.pollo.generators.get_image_path", return_value=None):
            gen = BaseVideoGenerator(api_key="k", project="p", prompt="x")
        with pytest.raises(ValueError, match="model_url"):
            gen.send_request()

    def test_get_valid_length_valid(self):
        assert Pollo20VideoGenerator._get_valid_length("10") == 10

    def test_get_valid_length_invalid(self):
        assert Pollo20VideoGenerator._get_valid_length("99") == 10  # default

    def test_get_valid_length_non_int(self):
        assert Pollo20VideoGenerator._get_valid_length("abc") == 10

    def test_get_valid_length_no_valid_lengths(self):
        """BaseVideoGenerator has no VALID_LENGTHS — any int should be accepted."""
        assert BaseVideoGenerator._get_valid_length("42") == 42

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_get_image_dimensions(self, *mocks):
        mock_img = MagicMock()
        mock_img.size = (1920, 1080)
        with patch("img2vid.pollo.generators.Image.open", return_value=mock_img):
            w, h = BaseVideoGenerator.get_image_dimensions(Path("/fake/image.jpg"))
        assert (w, h) == (1920, 1080)

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_get_aspect_ratio_from_image_no_valid_ratios(self, *mocks):
        """When VALID_RATIOS is empty, returns None."""
        gen = BaseVideoGenerator(api_key="k", project="p", prompt="x")
        gen.image_path = Path("/fake/image.jpg")
        assert gen.get_aspect_ratio_from_image() is None

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_get_aspect_ratio_from_image_no_image_path(self, *mocks):
        """When image_path is None, returns None."""
        gen = PolloDance20VideoGenerator(api_key="k", project="p", prompt="x")
        gen.image_path = None
        assert gen.get_aspect_ratio_from_image() is None



# ── Pollo20 ──────────────────────────────────────────────────────────

class TestPollo20VideoGenerator:
    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_payload(self, *mocks):
        gen = Pollo20VideoGenerator(
            api_key="k", project="p", prompt="hello",
            image_url=None, length=5, generate_audio=True, web_search=False,
        )
        payload = gen.get_payload()
        assert payload["input"]["length"] == 5
        assert payload["input"]["generateAudio"] is True
        assert payload["input"]["webSearch"] is False

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_valid_lengths(self, *mocks):
        assert Pollo20VideoGenerator.VALID_LENGTHS == (5, 10)

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_payload_with_image(self, *mocks):
        gen = Pollo20VideoGenerator(
            api_key="k", project="p", prompt="hello",
            image_url="https://img.com/i.jpg",
        )
        payload = gen.get_payload()
        assert payload["input"]["image"] == "https://img.com/i.jpg"


# ── PolloDance20 ─────────────────────────────────────────────────────

class TestPolloDance20VideoGenerator:
    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_model_url(self, *mocks):
        gen = PolloDance20VideoGenerator(api_key="k", project="p", prompt="x")
        assert "pollo-dance-2-0" in gen.model_url
        assert "fast" not in gen.model_url

    def test_valid_ratios(self):
        assert "4:3" in PolloDance20VideoGenerator.VALID_RATIOS
        assert "21:9" in PolloDance20VideoGenerator.VALID_RATIOS

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=Path("/fake/image.jpg"))
    @patch.object(BaseVideoGenerator, "get_image_dimensions", return_value=(1920, 1080))
    def test_auto_aspect_ratio_from_image(self, mock_dims, *mocks):
        gen = PolloDance20VideoGenerator(api_key="k", project="p", prompt="x")
        assert gen.aspect_ratio == "16:9"


class TestPolloDance20FastVideoGenerator:
    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_model_url_fast(self, *mocks):
        gen = PolloDance20FastVideoGenerator(api_key="k", project="p", prompt="x")
        assert "fast" in gen.model_url



# ── PolloDanceRef (ref2video) ────────────────────────────────────────

class TestPolloDanceRefVideoGenerator:
    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    @patch("img2vid.pollo.generators.get_subject_url", return_value=None)
    def test_payload_with_refs(self, *mocks):
        refs = [
            {"type": "image", "name": "char", "image": "https://img.com/a.jpg", "order": 1},
            {"type": "image", "name": "style", "image": "https://img.com/b.jpg", "order": 2},
        ]
        gen = PolloDanceRefVideoGenerator(
            api_key="k", project="p", prompt="hello",
            refs=refs, image_url=None,
        )
        payload = gen.get_payload()
        assert payload["input"]["refs"] == refs
        assert payload["input"]["duration"] == 10
        assert payload["input"]["videoNum"] == 1
        assert "ref2video" in gen.model_url

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    @patch("img2vid.pollo.generators.get_subject_url", return_value=None)
    def test_builds_refs_from_image_url(self, *mocks):
        gen = PolloDanceRefVideoGenerator(
            api_key="k", project="p", prompt="x",
            image_url="https://img.com/i.jpg",
        )
        assert len(gen.refs) == 1
        assert gen.refs[0]["image"] == "https://img.com/i.jpg"
        assert gen.refs[0]["type"] == "image"

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    @patch("img2vid.pollo.generators.get_subject_url", return_value=None)
    def test_is_text_only_no_refs(self, *mocks):
        gen = PolloDanceRefVideoGenerator(
            api_key="k", project="p", prompt="x",
            image_url=None,
        )
        assert gen.is_text_only is True

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    @patch("img2vid.pollo.generators.get_subject_url", return_value=None)
    def test_is_text_only_false_with_refs(self, *mocks):
        gen = PolloDanceRefVideoGenerator(
            api_key="k", project="p", prompt="x",
            image_url="https://img.com/i.jpg",
        )
        assert gen.is_text_only is False

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    @patch("img2vid.pollo.generators.get_subject_url", return_value=None)
    def test_video_num_clamped(self, *mocks):
        gen = PolloDanceRefVideoGenerator(
            api_key="k", project="p", prompt="x", image_url=None, video_num=5,
        )
        assert gen.video_num == 1

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    @patch("img2vid.pollo.generators.get_subject_url", return_value=None)
    def test_model_url(self, *mocks):
        gen = PolloDanceRefVideoGenerator(api_key="k", project="p", prompt="x", image_url=None)
        assert "ref2video" in gen.model_url


class TestPolloDanceRefFastVideoGenerator:
    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    @patch("img2vid.pollo.generators.get_subject_url", return_value=None)
    def test_model_url_fast(self, *mocks):
        gen = PolloDanceRefFastVideoGenerator(api_key="k", project="p", prompt="x", image_url=None)
        assert "fast" in gen.model_url
        assert "ref2video" in gen.model_url

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    @patch("img2vid.pollo.generators.get_subject_url", return_value=None)
    def test_inherits_ref_payload(self, *mocks):
        refs = [{"type": "image", "name": "char", "image": "https://img.com/a.jpg", "order": 1}]
        gen = PolloDanceRefFastVideoGenerator(
            api_key="k", project="p", prompt="hello",
            refs=refs, image_url=None,
        )
        payload = gen.get_payload()
        assert payload["input"]["refs"] == refs
        assert payload["input"]["duration"] == 10


