"""Tests for img2vid.common.spinner — CLI spinner utility."""
import sys
import time
import threading
import pytest
from unittest.mock import patch

from img2vid.common.spinner import Spinner


class TestSpinner:
    def test_init_defaults(self):
        s = Spinner()
        assert s.message == "Processing"
        assert s.delay == 0.1
        assert s.running is False
        assert len(s.spinner_chars) > 0

    def test_init_custom(self):
        s = Spinner(message="Loading", delay=0.5, spinner_chars=[".", ".."])
        assert s.message == "Loading"
        assert s.delay == 0.5
        assert s.spinner_chars == [".", ".."]

    def test_start_stop(self):
        s = Spinner(delay=0.01)
        s.start()
        assert s.running is True
        assert s._thread is not None
        assert s._start_time is not None
        time.sleep(0.05)
        s.stop()
        assert s.running is False
        assert s._elapsed > 0

    def test_stop_without_start(self):
        s = Spinner()
        # Should not raise
        s.stop()
        assert s.running is False

    def test_elapsed_time_tracked(self):
        s = Spinner(delay=0.01)
        s.start()
        time.sleep(0.1)
        s.stop()
        assert s._elapsed >= 0.05  # At least some time passed

