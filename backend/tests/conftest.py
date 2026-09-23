import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def isolated_admin_auth_store(tmp_path, monkeypatch):
    """Never change the developer's staff password/session store from tests."""
    monkeypatch.setattr(settings, "admin_auth_store_path", tmp_path / "auth.sqlite3")
