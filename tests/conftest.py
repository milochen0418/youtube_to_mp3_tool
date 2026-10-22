import pytest


@pytest.fixture
def audio_root(tmp_path, monkeypatch):
    """A private collection tree, our owner name, and no re-ddns node (so no quota calls)."""
    root = tmp_path / "collections"
    monkeypatch.setenv("DDNS_COLLECTIONS_ROOT", str(root))
    monkeypatch.setenv("DDNS_APP_ID", "youtube-to-mp3")
    monkeypatch.delenv("DDNS_COLLECTIONS_NODE_URL", raising=False)
    monkeypatch.delenv("RE_DDNS_API_URL", raising=False)
    return root
