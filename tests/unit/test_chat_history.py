"""Unit tests for per-persona chat history persistence."""
from __future__ import annotations

import json

import pytest

from playAIdes import PlayAIdes, PlayAIdesArgs, CHAT_HISTORY_CAP
from model_interfaces import MockLLM


@pytest.fixture
def play(persona_file, fake_tts, no_incarnation):
    """A PlayAIdes instance with use_avatar=True so the stub server is wired."""
    args = PlayAIdesArgs(
        persona=[str(persona_file)],
        generate_voice=False, use_voice=False,
        use_avatar=True, generate_avatar=False,
        llm=MockLLM(), tts=fake_tts,
    )
    return PlayAIdes(args)


class TestChatHistoryPersistence:
    def test_chat_histories_starts_empty(self, play):
        # The active persona's history is eagerly pre-loaded by
        # _load_persona_from_file → expect a single empty entry, not {}.
        assert play.chat_histories == {"testbot": []}

    def test_load_history_reads_existing_json(self, play, tmp_personas_dir):
        pid = "testbot"
        history_file = tmp_personas_dir / pid / "chat_history.json"
        history_file.write_text(json.dumps([
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]))
        # Active persona was eagerly pre-loaded by _load_persona_from_file
        # (with no on-disk history at the time). Clear that cache so the
        # newly-written history file is read.
        play.chat_histories.pop(pid, None)
        loaded = play._load_history(pid)
        assert loaded == [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        assert play.chat_histories[pid] == loaded

    def test_load_history_returns_empty_list_when_file_missing(self, play):
        assert play._load_history("nobody") == []
        assert play.chat_histories["nobody"] == []

    def test_load_history_caps_at_N_messages(self, play, tmp_personas_dir):
        pid = "testbot"
        history_file = tmp_personas_dir / pid / "chat_history.json"
        # Seed 200 messages — should be trimmed to the most recent N.
        big = [{"role": "user", "content": f"msg-{i}"} for i in range(200)]
        history_file.write_text(json.dumps(big))
        # Same eager-load consideration as above.
        play.chat_histories.pop(pid, None)
        loaded = play._load_history(pid)
        assert len(loaded) == CHAT_HISTORY_CAP
        # Most-recent retention: last message is preserved.
        assert loaded[-1] == {"role": "user", "content": "msg-199"}

    def test_save_history_round_trip(self, play, tmp_personas_dir):
        pid = "testbot"
        play.chat_histories[pid] = [
            {"role": "user", "content": "ping"},
            {"role": "assistant", "content": "pong"},
        ]
        play._save_history(pid)
        history_file = tmp_personas_dir / pid / "chat_history.json"
        assert history_file.exists()
        on_disk = json.loads(history_file.read_text())
        assert on_disk == play.chat_histories[pid]

    def test_save_history_is_atomic(self, play, tmp_personas_dir, monkeypatch):
        """If the write fails partway, the original file is left intact —
        atomic via NamedTemporaryFile + os.replace."""
        pid = "testbot"
        history_file = tmp_personas_dir / pid / "chat_history.json"
        history_file.write_text(json.dumps([{"role": "user", "content": "before"}]))
        play.chat_histories[pid] = [
            {"role": "user", "content": "after"},
        ]

        # Make os.replace fail to simulate a crash mid-write.
        import os as os_mod
        def boom(*a, **kw):
            raise OSError("disk full simulation")
        monkeypatch.setattr(os_mod, "replace", boom)

        with pytest.raises(OSError):
            play._save_history(pid)

        # Original file is untouched (no half-written content).
        on_disk = json.loads(history_file.read_text())
        assert on_disk == [{"role": "user", "content": "before"}]

        # Tempfile cleanup: no orphan .chat_history.*.json.tmp left behind
        # in the persona dir after the failed write.
        leftovers = list((tmp_personas_dir / pid).glob(".chat_history.*.json.tmp"))
        assert leftovers == [], f"orphan tempfile(s): {leftovers}"

    def test_delete_history_clears_memory_and_disk(self, play, tmp_personas_dir):
        pid = "testbot"
        play.chat_histories[pid] = [{"role": "user", "content": "x"}]
        play._save_history(pid)
        history_file = tmp_personas_dir / pid / "chat_history.json"
        assert history_file.exists()

        play.delete_history(pid)
        assert pid not in play.chat_histories
        assert not history_file.exists()
