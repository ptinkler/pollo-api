"""Tests for img2vid.pollo.generators — all video generator classes."""
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from img2vid.pollo.generators import (
    BaseVideoGenerator, Pollo20VideoGenerator, Pollo25VideoGenerator,
    PolloDance20VideoGenerator, PolloDance20FastVideoGenerator,
    PolloDanceRefVideoGenerator, PolloDanceRefFastVideoGenerator,
    Seedance25VideoGenerator, MinimaxH3VideoGenerator, Wan27VideoGenerator,
    Wan30VideoGenerator, Wan30PrimeVideoGenerator, MinimaxH3MaxVideoGenerator,
    BaseV1VideoGenerator, Pollo20VideoGeneratorV1, Pollo25VideoGeneratorV1,
    PolloDance20VideoGeneratorV1, PolloDance20FastVideoGeneratorV1,
    Seedance20VideoGeneratorV1, Seedance20FastVideoGeneratorV1,
    Seedance20MiniVideoGeneratorV1, Seedance25VideoGeneratorV1,
    MinimaxH3VideoGeneratorV1, Wan27VideoGeneratorV1, Wan30VideoGeneratorV1,
    Wan30PrimeVideoGeneratorV1,
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


class TestSeedance25VideoGenerator:
    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_model_url(self, *mocks):
        gen = Seedance25VideoGenerator(api_key="k", project="p", prompt="x")
        assert gen.model_url == "https://pollo.ai/api/platform/generation/bytedance/seedance-2-5"

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_valid_lengths_and_ratios(self, *mocks):
        # Confirmed against the live API's validation error responses.
        assert Seedance25VideoGenerator.VALID_LENGTHS == tuple(range(4, 31))
        assert Seedance25VideoGenerator.VALID_RATIOS == (
            "4:3", "3:4", "1:1", "16:9", "9:16", "21:9", "adaptive",
        )
        assert Seedance25VideoGenerator.VALID_RESOLUTIONS == ("480p", "720p")

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_default_resolution(self, *mocks):
        gen = Seedance25VideoGenerator(api_key="k", project="p", prompt="x")
        assert gen.resolution == "480p"

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_payload(self, *mocks):
        gen = Seedance25VideoGenerator(
            api_key="k", project="p", prompt="hello",
            image_url=None, length=20, resolution="720p", aspect_ratio="adaptive",
        )
        payload = gen.get_payload()
        assert payload["input"]["length"] == 20
        assert payload["input"]["resolution"] == "720p"
        assert payload["input"]["aspectRatio"] == "adaptive"

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=Path("/fake/image.jpg"))
    @patch.object(BaseVideoGenerator, "get_image_dimensions", return_value=(1920, 1080))
    def test_auto_aspect_ratio_from_image_skips_adaptive(self, mock_dims, *mocks):
        # "adaptive" has no ":" and must be excluded from closest-ratio matching.
        gen = Seedance25VideoGenerator(api_key="k", project="p", prompt="x")
        assert gen.aspect_ratio == "16:9"


class TestMinimaxH3VideoGenerator:
    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_model_url(self, *mocks):
        gen = MinimaxH3VideoGenerator(api_key="k", project="p", prompt="x")
        assert gen.model_url == "https://pollo.ai/api/platform/generation/minimax/minimax-h3"

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_valid_lengths(self, *mocks):
        assert MinimaxH3VideoGenerator.VALID_LENGTHS == tuple(range(4, 16))

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_text_to_video_payload(self, *mocks):
        gen = MinimaxH3VideoGenerator(
            api_key="k", project="p", prompt="hello",
            image_url=None, length=8, resolution="1080p", prompt_optimizer=False,
        )
        payload = gen.get_payload()
        assert payload["input"]["prompt"] == "hello"
        assert payload["input"]["length"] == 8
        assert payload["input"]["resolution"] == "1080p"
        assert payload["input"]["promptOptimizer"] is False
        assert "image" not in payload["input"]

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_image_to_video_payload(self, *mocks):
        gen = MinimaxH3VideoGenerator(
            api_key="k", project="p", prompt="hello",
            image_url="https://img.com/i.jpg", image_tail="https://img.com/tail.jpg",
        )
        payload = gen.get_payload()
        assert payload["input"]["image"] == "https://img.com/i.jpg"
        assert payload["input"]["imageTail"] == "https://img.com/tail.jpg"

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_default_resolution(self, *mocks):
        # Confirmed against the live API: "480P" | "768P" | "2K" are accepted, default stays "2K".
        gen = MinimaxH3VideoGenerator(api_key="k", project="p", prompt="x")
        assert gen.resolution == "2K"
        assert MinimaxH3VideoGenerator.VALID_RESOLUTIONS == ("480P", "768P", "2K")


class TestWan27VideoGenerator:
    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    @patch("img2vid.pollo.generators.get_audio_url", return_value=None)
    def test_model_url(self, *mocks):
        gen = Wan27VideoGenerator(api_key="k", project="p", prompt="x")
        assert gen.model_url == "https://pollo.ai/api/platform/generation/wanx/wan-v2-7"

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    @patch("img2vid.pollo.generators.get_audio_url", return_value=None)
    def test_valid_lengths_and_resolutions(self, *mocks):
        assert Wan27VideoGenerator.VALID_LENGTHS == tuple(range(2, 16))
        assert Wan27VideoGenerator.VALID_RESOLUTIONS == ("720P", "1080P")

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    @patch("img2vid.pollo.generators.get_audio_url", return_value=None)
    def test_defaults(self, *mocks):
        gen = Wan27VideoGenerator(api_key="k", project="p", prompt="x")
        assert gen.resolution == "1080P"
        assert gen.length == 5

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    @patch("img2vid.pollo.generators.get_audio_url", return_value=None)
    def test_image_to_video_payload(self, *mocks):
        gen = Wan27VideoGenerator(
            api_key="k", project="p", prompt="hello",
            image_url="https://img.com/i.jpg", image_tail="https://img.com/tail.jpg",
            length=10, resolution="720P", seed=42, negative_prompt="blurry",
        )
        payload = gen.get_payload()
        assert payload["input"]["image"] == "https://img.com/i.jpg"
        assert payload["input"]["imageTail"] == "https://img.com/tail.jpg"
        assert payload["input"]["length"] == 10
        assert payload["input"]["resolution"] == "720P"
        assert payload["input"]["seed"] == 42
        assert payload["input"]["negativePrompt"] == "blurry"

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    @patch("img2vid.pollo.generators.get_audio_url", return_value=None)
    def test_text_only_payload_omits_image(self, *mocks):
        gen = Wan27VideoGenerator(api_key="k", project="p", prompt="hello", image_url=None)
        payload = gen.get_payload()
        assert "image" not in payload["input"]

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    @patch("img2vid.pollo.generators.get_audio_url", return_value=None)
    def test_audio_url_payload(self, *mocks):
        gen = Wan27VideoGenerator(
            api_key="k", project="p", prompt="hello", audio_url="https://a.com/audio.mp3",
        )
        payload = gen.get_payload()
        assert payload["input"]["audioUrl"] == "https://a.com/audio.mp3"


class TestWan30VideoGenerator:
    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_model_url(self, *mocks):
        gen = Wan30VideoGenerator(api_key="k", project="p", prompt="x")
        assert gen.model_url == "https://pollo.ai/api/platform/generation/wanx/wan-v3-0"

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_valid_lengths_and_resolutions(self, *mocks):
        # Confirmed against the live API's validation error responses.
        assert Wan30VideoGenerator.VALID_LENGTHS == tuple(range(2, 31))
        assert Wan30VideoGenerator.VALID_RESOLUTIONS == ("480P", "720P", "1080P")
        assert Wan30VideoGenerator.VALID_NUM_OUTPUTS == (1, 2, 3, 4)

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_defaults(self, *mocks):
        gen = Wan30VideoGenerator(api_key="k", project="p", prompt="x")
        assert gen.resolution == "1080P"
        assert gen.length == 5
        assert gen.generate_audio is True
        assert gen.num_outputs == 1

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_text_to_video_payload(self, *mocks):
        gen = Wan30VideoGenerator(
            api_key="k", project="p", prompt="hello",
            image_url=None, length=30, resolution="480P",
            generate_audio=False, num_outputs=4,
        )
        payload = gen.get_payload()
        assert payload["input"]["prompt"] == "hello"
        assert payload["input"]["length"] == 30
        assert payload["input"]["resolution"] == "480P"
        assert payload["input"]["generateAudio"] is False
        assert payload["input"]["numOutputs"] == 4
        assert "image" not in payload["input"]

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_image_to_video_payload(self, *mocks):
        gen = Wan30VideoGenerator(
            api_key="k", project="p", prompt="hello", image_url="https://img.com/i.jpg",
        )
        payload = gen.get_payload()
        assert payload["input"]["image"] == "https://img.com/i.jpg"

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_num_outputs_clamped(self, *mocks):
        gen = Wan30VideoGenerator(api_key="k", project="p", prompt="x", num_outputs=99)
        assert gen.num_outputs == 4
        gen2 = Wan30VideoGenerator(api_key="k", project="p", prompt="x", num_outputs=0)
        assert gen2.num_outputs == 1


class TestWan30PrimeVideoGenerator:
    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_model_url(self, *mocks):
        gen = Wan30PrimeVideoGenerator(api_key="k", project="p", prompt="x")
        assert gen.model_url == "https://pollo.ai/api/platform/generation/wanx/wan-v3-0-prime"

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_inherits_wan30_schema(self, *mocks):
        # Confirmed against the live API: same enums/types as wan-v3-0.
        assert Wan30PrimeVideoGenerator.VALID_LENGTHS == tuple(range(2, 31))
        assert Wan30PrimeVideoGenerator.VALID_RESOLUTIONS == ("480P", "720P", "1080P")

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_text_to_video_payload(self, *mocks):
        gen = Wan30PrimeVideoGenerator(
            api_key="k", project="p", prompt="hello",
            image_url=None, length=30, resolution="480P",
            generate_audio=False, num_outputs=4,
        )
        payload = gen.get_payload()
        assert payload["input"]["prompt"] == "hello"
        assert payload["input"]["length"] == 30
        assert payload["input"]["resolution"] == "480P"
        assert payload["input"]["generateAudio"] is False
        assert payload["input"]["numOutputs"] == 4
        assert "image" not in payload["input"]


class TestMinimaxH3MaxVideoGenerator:
    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_model_url(self, *mocks):
        gen = MinimaxH3MaxVideoGenerator(api_key="k", project="p", prompt="x")
        assert gen.model_url == "https://pollo.ai/api/platform/v1/generation/minimax/minimax-h3-max/video"

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_valid_lengths_and_resolutions(self, *mocks):
        # Confirmed against the live API's validation error responses.
        assert MinimaxH3MaxVideoGenerator.VALID_LENGTHS == (5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15)
        assert MinimaxH3MaxVideoGenerator.VALID_RESOLUTIONS == ("480p", "768p", "1080p")

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_text_to_video_payload_uses_duration_key(self, *mocks):
        gen = MinimaxH3MaxVideoGenerator(
            api_key="k", project="p", prompt="hello",
            image_url=None, length=8, resolution="768p",
        )
        payload = gen.get_payload()
        assert payload["input"]["prompt"] == "hello"
        assert payload["input"]["duration"] == 8
        assert payload["input"]["resolution"] == "768p"
        assert "length" not in payload["input"]
        assert "image" not in payload["input"]

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_image_to_video_payload(self, *mocks):
        gen = MinimaxH3MaxVideoGenerator(
            api_key="k", project="p", prompt="hello", image_url="https://img.com/i.jpg",
        )
        payload = gen.get_payload()
        assert payload["input"]["image"] == "https://img.com/i.jpg"

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_default_resolution(self, *mocks):
        # Matches the OpenAPI spec's own default ("480p"), not an arbitrary choice.
        gen = MinimaxH3MaxVideoGenerator(api_key="k", project="p", prompt="x")
        assert gen.resolution == "480p"


class TestPollo25VideoGenerator:
    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_model_url(self, *mocks):
        gen = Pollo25VideoGenerator(api_key="k", project="p", prompt="x")
        assert gen.model_url == "https://pollo.ai/api/platform/generation/pollo/pollo-v2-5"

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_default_resolution(self, *mocks):
        # Confirmed against the live API: "480p" is rejected, only 720p/1080p accepted.
        gen = Pollo25VideoGenerator(api_key="k", project="p", prompt="x")
        assert gen.resolution == "1080p"
        assert Pollo25VideoGenerator.VALID_RESOLUTIONS == ("720p", "1080p")

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_valid_lengths(self, *mocks):
        # Confirmed against the live API: not the (5, 10) inherited from Pollo 2.0 —
        # 13/14 are absent while 15 is present.
        assert Pollo25VideoGenerator.VALID_LENGTHS == (4, 5, 6, 7, 8, 9, 10, 11, 12, 15)

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_payload(self, *mocks):
        gen = Pollo25VideoGenerator(
            api_key="k", project="p", prompt="hello", resolution="720p", length=5,
        )
        payload = gen.get_payload()
        assert payload["input"]["resolution"] == "720p"
        assert payload["input"]["length"] == 5
        # aspectRatio has no effect on Pollo 2.5's output per user report — dropped, not sent.
        assert "aspectRatio" not in payload["input"]


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




# ── v1 API generators ────────────────────────────────────────────────

class TestPollo20VideoGeneratorV1:
    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_model_url(self, *mocks):
        gen = Pollo20VideoGeneratorV1(api_key="k", project="p", prompt="x")
        assert gen.model_url == "https://pollo.ai/api/platform/v1/generation/pollo-ai/pollo-v2/video"

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_text_to_video_payload_uses_duration(self, *mocks):
        gen = Pollo20VideoGeneratorV1(
            api_key="k", project="p", prompt="hello", image_url=None, length=10,
            resolution="1080p", aspect_ratio="4:3", seed=7,
        )
        payload = gen.get_payload()
        assert payload["input"]["prompt"] == "hello"
        assert payload["input"]["duration"] == 10
        assert "length" not in payload["input"]
        assert payload["input"]["resolution"] == "1080p"
        assert payload["input"]["aspectRatio"] == "4:3"
        assert payload["input"]["seed"] == 7
        assert payload["input"]["generateAudio"] is True
        assert "webSearch" not in payload["input"]  # v1 pollo-v2 has no webSearch field

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_image_to_video_payload_omits_aspect_ratio(self, *mocks):
        gen = Pollo20VideoGeneratorV1(
            api_key="k", project="p", prompt="hello", image_url="https://img.com/i.jpg",
        )
        payload = gen.get_payload()
        assert payload["input"]["image"] == "https://img.com/i.jpg"
        assert "aspectRatio" not in payload["input"]

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_refs_payload(self, *mocks):
        gen = Pollo20VideoGeneratorV1(
            api_key="k", project="p", prompt="hello", image_url=None,
            refs=[{"url": "https://img.com/a.jpg", "type": "image"}, {"url": "  "}],
        )
        payload = gen.get_payload()
        assert payload["input"]["refs"] == [{"url": "https://img.com/a.jpg", "type": "image"}]
        assert "image" not in payload["input"]
        assert payload["input"]["aspectRatio"]  # refs branch includes aspectRatio too


class TestPollo25VideoGeneratorV1:
    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_model_url_and_mode(self, *mocks):
        gen = Pollo25VideoGeneratorV1(api_key="k", project="p", prompt="x")
        assert gen.model_url == "https://pollo.ai/api/platform/v1/generation/pollo-ai/pollo-v2-5/video"
        assert gen.mode == "basic"
        payload = gen.get_payload()
        assert payload["input"]["mode"] == "basic"
        assert "seed" not in payload["input"]  # no seed field for pollo25 v1

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_custom_mode(self, *mocks):
        gen = Pollo25VideoGeneratorV1(api_key="k", project="p", prompt="x", mode="pro")
        payload = gen.get_payload()
        assert payload["input"]["mode"] == "pro"


class TestPolloDance20VideoGeneratorV1:
    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_model_url(self, *mocks):
        gen = PolloDance20VideoGeneratorV1(api_key="k", project="p", prompt="x")
        assert gen.model_url == "https://pollo.ai/api/platform/v1/generation/pollo-ai/pollo-dance-2-0/video"

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_image_to_video_with_tail(self, *mocks):
        gen = PolloDance20VideoGeneratorV1(
            api_key="k", project="p", prompt="hello",
            image_url="https://img.com/i.jpg", image_tail="https://img.com/tail.jpg",
            web_search=True, seed=3,
        )
        payload = gen.get_payload()
        assert payload["input"]["imageTail"] == "https://img.com/tail.jpg"
        assert payload["input"]["webSearch"] is True
        assert payload["input"]["seed"] == 3


class TestPolloDance20FastVideoGeneratorV1:
    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_model_url_and_resolutions(self, *mocks):
        gen = PolloDance20FastVideoGeneratorV1(api_key="k", project="p", prompt="x")
        assert gen.model_url == "https://pollo.ai/api/platform/v1/generation/pollo-ai/pollo-dance-2-0-fast/video"
        assert PolloDance20FastVideoGeneratorV1.VALID_RESOLUTIONS == ("480p", "720p")


class TestSeedance20VideoGeneratorV1:
    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_model_url_and_resolutions(self, *mocks):
        gen = Seedance20VideoGeneratorV1(api_key="k", project="p", prompt="x")
        assert gen.model_url == "https://pollo.ai/api/platform/v1/generation/bytedance/seedance-2-0/video"
        assert Seedance20VideoGeneratorV1.VALID_RESOLUTIONS == ("480p", "720p", "1080p", "4K")


class TestSeedance20FastAndMiniVideoGeneratorV1:
    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_fast_model_url(self, *mocks):
        gen = Seedance20FastVideoGeneratorV1(api_key="k", project="p", prompt="x")
        assert gen.model_url == "https://pollo.ai/api/platform/v1/generation/bytedance/seedance-2-0-fast/video"
        assert Seedance20FastVideoGeneratorV1.VALID_RESOLUTIONS == ("480p", "720p")

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_mini_model_url(self, *mocks):
        gen = Seedance20MiniVideoGeneratorV1(api_key="k", project="p", prompt="x")
        assert gen.model_url == "https://pollo.ai/api/platform/v1/generation/bytedance/seedance-2-0-mini/video"
        assert Seedance20MiniVideoGeneratorV1.VALID_RESOLUTIONS == ("480p", "720p")


class TestSeedance25VideoGeneratorV1:
    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_model_url(self, *mocks):
        gen = Seedance25VideoGeneratorV1(api_key="k", project="p", prompt="x")
        assert gen.model_url == "https://pollo.ai/api/platform/v1/generation/bytedance/seedance-2-5/video"
        assert Seedance25VideoGeneratorV1.VALID_LENGTHS == tuple(range(4, 31))

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_default_aspect_ratio_is_adaptive(self, *mocks):
        gen = Seedance25VideoGeneratorV1(api_key="k", project="p", prompt="x", image_url=None)
        assert gen.aspect_ratio == "adaptive"
        payload = gen.get_payload()
        assert payload["input"]["aspectRatio"] == "adaptive"

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_explicit_aspect_ratio_overrides_default(self, *mocks):
        gen = Seedance25VideoGeneratorV1(
            api_key="k", project="p", prompt="x", image_url=None, aspect_ratio="16:9",
        )
        assert gen.aspect_ratio == "16:9"


class TestMinimaxH3VideoGeneratorV1:
    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_model_url_and_resolutions(self, *mocks):
        gen = MinimaxH3VideoGeneratorV1(api_key="k", project="p", prompt="x")
        assert gen.model_url == "https://pollo.ai/api/platform/v1/generation/minimax/minimax-h3/video"
        # Lowercase below 2K in v1, same tiers as legacy MinimaxH3VideoGenerator's "480P"/"768P"/"2K"
        assert MinimaxH3VideoGeneratorV1.VALID_RESOLUTIONS == ("480p", "768p", "2K")

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_no_generate_audio_or_web_search(self, *mocks):
        gen = MinimaxH3VideoGeneratorV1(api_key="k", project="p", prompt="x", image_url=None)
        payload = gen.get_payload()
        assert "generateAudio" not in payload["input"]
        assert "webSearch" not in payload["input"]
        assert "seed" not in payload["input"]


class TestWan27VideoGeneratorV1:
    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    @patch("img2vid.pollo.generators.get_audio_url", return_value=None)
    def test_model_url_uses_alibaba_provider(self, *mocks):
        gen = Wan27VideoGeneratorV1(api_key="k", project="p", prompt="x")
        assert gen.model_url == "https://pollo.ai/api/platform/v1/generation/alibaba/wan-v2-7/video"
        assert Wan27VideoGeneratorV1.VALID_RESOLUTIONS == ("720p", "1080p")

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    @patch("img2vid.pollo.generators.get_audio_url", return_value=None)
    def test_negative_prompt_and_audio_driven_generation(self, *mocks):
        gen = Wan27VideoGeneratorV1(
            api_key="k", project="p", prompt="hello", image_url=None,
            negative_prompt="blurry", audio_url="https://a.com/audio.mp3",
        )
        payload = gen.get_payload()
        assert payload["input"]["negativePrompt"] == "blurry"
        assert payload["input"]["audio"] == "https://a.com/audio.mp3"
        assert "generateAudio" not in payload["input"]  # wan27 has no generateAudio field


class TestWan30VideoGeneratorV1:
    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_model_url_uses_alibaba_provider(self, *mocks):
        gen = Wan30VideoGeneratorV1(api_key="k", project="p", prompt="x")
        assert gen.model_url == "https://pollo.ai/api/platform/v1/generation/alibaba/wan-v3-0/video"
        assert Wan30VideoGeneratorV1.VALID_RESOLUTIONS == ("480p", "720p", "1080p")

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_num_outputs_dropped_and_seed_gained(self, *mocks):
        # v1's schema has no numOutputs field at all (legacy's was already
        # flagged unconfirmed) but does gain `seed`, unlike legacy Wan30.
        gen = Wan30VideoGeneratorV1(api_key="k", project="p", prompt="x", image_url=None, seed=99)
        assert not hasattr(gen, "num_outputs")
        payload = gen.get_payload()
        assert "numOutputs" not in payload["input"]
        assert payload["input"]["seed"] == 99


class TestWan30PrimeVideoGeneratorV1:
    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_model_url(self, *mocks):
        gen = Wan30PrimeVideoGeneratorV1(api_key="k", project="p", prompt="x")
        assert gen.model_url == "https://pollo.ai/api/platform/v1/generation/alibaba/wan-v3-0-prime/video"
        # Inherits wan30's schema unchanged
        assert Wan30PrimeVideoGeneratorV1.VALID_LENGTHS == tuple(range(2, 31))
        assert Wan30PrimeVideoGeneratorV1.VALID_RESOLUTIONS == ("480p", "720p", "1080p")


class TestBaseV1VideoGeneratorRefsNormalization:
    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_refs_without_has_refs_flag_are_ignored(self, *mocks):
        # Pollo 2.5 v1 has no Reference-To-Video branch (HAS_REFS=False),
        # so a refs kwarg must be silently dropped rather than sent.
        gen = Pollo25VideoGeneratorV1(
            api_key="k", project="p", prompt="hello", image_url=None,
            refs=[{"url": "https://img.com/a.jpg"}],
        )
        assert gen.refs is None
        payload = gen.get_payload()
        assert "refs" not in payload["input"]

    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_refs_fallback_to_legacy_shaped_dicts(self, *mocks):
        # A legacy-shaped ref dict ({"image": url}) still yields a valid
        # v1-shaped ref ({"url": url}) via the image/video/audio fallback.
        gen = Pollo20VideoGeneratorV1(
            api_key="k", project="p", prompt="hello", image_url=None,
            refs=[{"type": "image", "image": "https://img.com/a.jpg"}],
        )
        payload = gen.get_payload()
        assert payload["input"]["refs"] == [{"url": "https://img.com/a.jpg", "type": "image"}]
