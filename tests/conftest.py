"""Global test fixtures — prevent tests from touching the real database or assets."""
import pytest


@pytest.fixture(autouse=True)
def _guard_real_db(monkeypatch, tmp_path):
    """Redirect config paths to a temp directory so no test can accidentally
    create files in the real data/assets directories."""
    import img2vid.common.config as config_mod

    monkeypatch.setattr(config_mod, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(config_mod, "ASSETS_DIR", tmp_path / "assets")
    monkeypatch.setattr(config_mod, "DB_PATH", tmp_path / "data" / "metadata.db")

