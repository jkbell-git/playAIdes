"""Hermetic unit tests for backend.stores.history.HistoryStore."""
from __future__ import annotations

import json
import os

import pytest

from backend.stores.history import HistoryStore


@pytest.fixture
def store(tmp_path):
    return HistoryStore(base_dir=tmp_path / "personas")


def test_missing_file_reads_empty(store):
    assert store.read("nobody") == []


def test_write_read_round_trip(store):
    history = [{"role": "user", "content": "hi"}]
    store.write("alpha", history)
    assert store.read("alpha") == history


def test_corrupt_file_warns_and_reads_empty(store, tmp_path):
    d = tmp_path / "personas" / "alpha"
    d.mkdir(parents=True)
    (d / "chat_history.json").write_text("{not json")
    assert store.read("alpha") == []


def test_write_is_atomic_and_cleans_up_tempfile(store, tmp_path, monkeypatch):
    store.write("alpha", [{"role": "user", "content": "before"}])

    def boom(*a, **kw):
        raise OSError("disk full simulation")
    monkeypatch.setattr(os, "replace", boom)

    with pytest.raises(OSError):
        store.write("alpha", [{"role": "user", "content": "after"}])

    path = tmp_path / "personas" / "alpha" / "chat_history.json"
    assert json.loads(path.read_text()) == [{"role": "user", "content": "before"}]
    leftovers = list((tmp_path / "personas" / "alpha").glob(".chat_history.*.json.tmp"))
    assert leftovers == [], f"orphan tempfile(s): {leftovers}"


def test_delete_removes_file_and_tolerates_missing(store, tmp_path):
    store.write("alpha", [{"role": "user", "content": "x"}])
    store.delete("alpha")
    assert not (tmp_path / "personas" / "alpha" / "chat_history.json").exists()
    store.delete("alpha")  # second delete is a no-op


@pytest.mark.parametrize("bad_id", ["", ".", "..", "a/b", "a\\b"])
def test_traversal_guard_rejects(store, bad_id):
    with pytest.raises(ValueError):
        store.read(bad_id)
    with pytest.raises(ValueError):
        store.write(bad_id, [])
    with pytest.raises(ValueError):
        store.delete(bad_id)
