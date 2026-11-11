"""Tests for web.media_types — the one place that says what a file is.

These sets used to live in six modules, which is how a .webm could be a video
in one and fall through to "image" in another.
"""

import pytest

from web.media_types import AUDIO_SUFFIXES, IMAGE_SUFFIXES, VIDEO_SUFFIXES, kind_of


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("a.png", "image"),
        ("a.JPG", "image"),
        ("a.webp", "image"),
        ("a.gif", "image"),
        ("a.svg", "image"),
        ("a.mp4", "video"),
        ("a.webm", "video"),  # read as an image before these were shared
        ("a.MOV", "video"),
        ("a.mp3", "audio"),
        ("a.wav", "audio"),
        ("a.m4a", "audio"),
        ("a.ogg", "audio"),
        ("a.txt", None),
        ("noextension", None),
    ],
)
def test_kind_of(name, kind):
    assert kind_of(name) == kind


def test_the_three_sets_do_not_overlap():
    assert not IMAGE_SUFFIXES & VIDEO_SUFFIXES
    assert not IMAGE_SUFFIXES & AUDIO_SUFFIXES
    assert not VIDEO_SUFFIXES & AUDIO_SUFFIXES
