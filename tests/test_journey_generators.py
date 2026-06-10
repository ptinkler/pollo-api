"""Tests for PolloJourneyImageGenerator."""
import pytest
from unittest.mock import patch

from img2vid.pollo.generators import PolloJourneyImageGenerator
from img2vid.pollo.pollo_img2vid import IMAGE_GENERATORS, get_image_generator


class TestPolloJourneyImageGenerator:
    def _make(self, **kwargs):
        with patch("img2vid.pollo.generators.get_prompt", return_value="test prompt"), \
             patch("img2vid.pollo.generators.get_image_url", return_value=None), \
             patch("img2vid.pollo.generators.get_image_path", return_value=None):
            return PolloJourneyImageGenerator(api_key="k", project="p", **kwargs)

    def test_model_url(self):
        gen = self._make(prompt="x")
        assert "pollojourney" in gen.model_url
        assert "pollojourney-v7-image" in gen.model_url

    def test_text_only_payload(self):
        gen = self._make(prompt="a sunset", image_url=None)
        payload = gen.get_payload()
        assert payload["input"]["prompt"] == "a sunset"
        assert "imageUrl" not in payload["input"]
        assert "images" not in payload["input"]

    def test_text_only_with_style(self):
        gen = self._make(prompt="a sunset", image_url=None, style="anime")
        payload = gen.get_payload()
        assert payload["input"]["style"] == "anime"

    def test_image_to_image_payload(self):
        gen = self._make(prompt="transform", image_url="https://example.com/img.jpg")
        payload = gen.get_payload()
        assert payload["input"]["imageUrl"] == "https://example.com/img.jpg"
        assert "images" not in payload["input"]

    def test_multi_image_payload(self):
        imgs = ["https://example.com/a.jpg", "https://example.com/b.jpg"]
        gen = self._make(prompt="blend", images=imgs, image_url=None)
        payload = gen.get_payload()
        assert payload["input"]["images"] == imgs
        assert "imageUrl" not in payload["input"]

    def test_multi_image_with_image_url(self):
        imgs = ["https://example.com/a.jpg"]
        gen = self._make(prompt="blend", images=imgs, image_url="https://example.com/base.jpg")
        payload = gen.get_payload()
        assert payload["input"]["images"] == imgs
        assert payload["input"]["imageUrl"] == "https://example.com/base.jpg"

    def test_aspect_ratio_default(self):
        gen = self._make(prompt="x", image_url=None)
        assert gen.aspect_ratio == "1:1"

    def test_aspect_ratio_override(self):
        gen = self._make(prompt="x", image_url=None, aspect_ratio="16:9")
        assert gen.aspect_ratio == "16:9"
        payload = gen.get_payload()
        assert payload["input"]["aspectRatio"] == "16:9"

    def test_seed_in_payload(self):
        gen = self._make(prompt="x", image_url=None, seed=42)
        payload = gen.get_payload()
        assert payload["input"]["seed"] == 42

    def test_no_seed_omitted(self):
        gen = self._make(prompt="x", image_url=None)
        payload = gen.get_payload()
        assert "seed" not in payload["input"]

    def test_is_text_only_no_image(self):
        gen = self._make(prompt="x", image_url=None)
        assert gen.is_text_only is True

    def test_is_text_only_with_image_url(self):
        gen = self._make(prompt="x", image_url="https://example.com/img.jpg")
        assert gen.is_text_only is False

    def test_is_text_only_with_images(self):
        gen = self._make(prompt="x", images=["https://example.com/img.jpg"], image_url=None)
        assert gen.is_text_only is False

    def test_valid_ratios(self):
        assert "1:1" in PolloJourneyImageGenerator.VALID_RATIOS
        assert "16:9" in PolloJourneyImageGenerator.VALID_RATIOS
        assert "9:16" in PolloJourneyImageGenerator.VALID_RATIOS

    def test_style_not_added_for_img2img(self):
        gen = self._make(prompt="x", image_url="https://example.com/img.jpg", style="anime")
        payload = gen.get_payload()
        # style is only included in text-to-image mode
        assert "style" not in payload["input"]


class TestImageGeneratorsRegistry:
    def test_pollojourney_in_registry(self):
        assert "pollojourney" in IMAGE_GENERATORS

    def test_get_image_generator(self):
        with patch("img2vid.pollo.generators.get_prompt", return_value="p"), \
             patch("img2vid.pollo.generators.get_image_url", return_value=None), \
             patch("img2vid.pollo.generators.get_image_path", return_value=None):
            gen = get_image_generator("pollojourney", api_key="k", project="p", prompt="test")
        assert isinstance(gen, PolloJourneyImageGenerator)

    def test_get_image_generator_unknown(self):
        with pytest.raises(ValueError, match="Unsupported image model"):
            get_image_generator("unknown_model")
