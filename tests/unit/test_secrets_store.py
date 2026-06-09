from pathlib import Path

from backend.stores import secrets_store


def test_set_then_get_secret(tmp_path: Path):
    path = str(tmp_path / "config" / "secrets.json")
    secrets_store.set_secret("homeassistant", "token", "shhh", path)
    assert secrets_store.get_secret("homeassistant", "token", path) == "shhh"


def test_get_missing_secret_returns_none(tmp_path: Path):
    path = str(tmp_path / "secrets.json")
    assert secrets_store.get_secret("homeassistant", "token", path) is None


def test_resolve_token_prefers_file_over_env(tmp_path: Path):
    path = str(tmp_path / "secrets.json")
    secrets_store.set_secret("homeassistant", "token", "from-file", path)
    tok = secrets_store.resolve_token("homeassistant", path, env={"HA_TOKEN": "from-env"})
    assert tok == "from-file"


def test_resolve_token_falls_back_to_env(tmp_path: Path):
    path = str(tmp_path / "secrets.json")  # no file written
    tok = secrets_store.resolve_token("homeassistant", path, env={"HA_TOKEN": "from-env"})
    assert tok == "from-env"
