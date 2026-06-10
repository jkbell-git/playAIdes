"""Hermetic unit tests for backend.stores.personas.PersonaStore."""
from __future__ import annotations

import json

import pytest

from backend.stores.personas import PersonaStore


@pytest.fixture
def store(tmp_path):
    return PersonaStore(base_dir=tmp_path / "personas")


def test_write_read_round_trip(store):
    store.write("alpha", {"name": "Alpha"})
    assert store.read("alpha") == {"name": "Alpha"}
    assert store.exists("alpha") is True


def test_read_missing_raises_keyerror(store):
    with pytest.raises(KeyError):
        store.read("ghost")
    assert store.exists("ghost") is False


def test_list_ids_only_dirs_with_persona_json(store, tmp_path):
    store.write("alpha", {"name": "A"})
    store.write("beta", {"name": "B"})
    (tmp_path / "personas" / "empty_dir").mkdir()
    (tmp_path / "personas" / "stray.txt").write_text("hi")
    assert store.list_ids() == ["alpha", "beta"]


def test_list_ids_creates_base_dir(tmp_path):
    base = tmp_path / "not_yet"
    store = PersonaStore(base_dir=base)
    assert store.list_ids() == []
    assert base.is_dir()


def test_delete_removes_directory(store, tmp_path):
    store.write("alpha", {"name": "A"})
    store.delete("alpha")
    assert not (tmp_path / "personas" / "alpha").exists()


def test_delete_missing_raises_keyerror(store):
    with pytest.raises(KeyError):
        store.delete("ghost")


@pytest.mark.parametrize("bad_id", ["", ".", "..", "../etc", "a/b", "a\\b"])
def test_traversal_guard_rejects(store, bad_id):
    with pytest.raises(ValueError):
        store.read(bad_id)
    with pytest.raises(ValueError):
        store.write(bad_id, {})
    with pytest.raises(ValueError):
        store.delete(bad_id)
    with pytest.raises(ValueError):
        store.exists(bad_id)


def test_write_pretty_prints(store, tmp_path):
    store.write("alpha", {"name": "A"})
    text = (tmp_path / "personas" / "alpha" / "persona.json").read_text()
    assert text == json.dumps({"name": "A"}, indent=2)
