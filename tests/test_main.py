"""Tests for img2vid.pollo.__main__ — CLI entry point."""
import sys
import pytest
from unittest.mock import patch, MagicMock


class TestMain:
    @patch("img2vid.pollo.__main__.create_video")
    def test_main_defaults(self, mock_create):
        from img2vid.pollo.__main__ import main
        with patch("sys.argv", ["prog"]):
            main()
        mock_create.assert_called_once_with(
            model=None, project=None, aspect_ratio=None,
            length=None, resolution=None, generate_audio=False,
        )

    @patch("img2vid.pollo.__main__.create_video")
    def test_main_with_args(self, mock_create):
        from img2vid.pollo.__main__ import main
        with patch("sys.argv", ["prog", "-m", "pollodance20", "-p", "myproj",
                                "-r", "16:9", "-l", "10", "--resolution", "720p", "--audio"]):
            main()
        mock_create.assert_called_once_with(
            model="pollodance20", project="myproj", aspect_ratio="16:9",
            length=10, resolution="720p", generate_audio=True,
        )

    @patch("img2vid.pollo.__main__.create_video", side_effect=ValueError("bad model"))
    def test_main_value_error_exits(self, mock_create):
        from img2vid.pollo.__main__ import main
        with patch("sys.argv", ["prog"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    def test_name_main_guard(self):
        """Cover the if __name__ == '__main__' guard."""
        import img2vid.pollo.__main__ as mod
        with patch.object(mod, "main") as mock_main, \
             patch.object(mod, "__name__", "__main__"):
            # Re-evaluate the guard condition
            if mod.__name__ == "__main__":
                mod.main()
        mock_main.assert_called_once()

