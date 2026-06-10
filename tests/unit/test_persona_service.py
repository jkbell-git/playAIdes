"""PersonaService unit tests — real stores on tmp dirs (hermetic)."""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from backend.services.persona import (
    PersonaActive, PersonaExists, PersonaNotFound, PersonaService, slug,
)
from backend.stores.history import HistoryStore
from backend.stores.personas import PersonaStore

VALID = {
    "name": "TestBot", "back_ground": "bg",
    "psyche": {"traits": []}, "gender": "Female", "language": "English",
}


@pytest.fixture
def base(tmp_path):
    return tmp_path / "personas"


@pytest.fixture
def svc(base):
    return PersonaService(
        persona_store=PersonaStore(base_dir=base),
        history_store=HistoryStore(base_dir=base),
        active_persona_id=lambda: "active_bot",
        history_cap=5,
    )


def _seed(base, pid, doc=None):
    d = base / pid
    d.mkdir(parents=True)
    (d / "persona.json").write_text(json.dumps(doc or VALID))


def test_slug_rule():
    assert slug("  New Friend ") == "new_friend"


class TestCrud:
    def test_create_writes_full_defaulted_doc(self, svc, base):
        out = svc.create("New Friend", "A brand new persona.")
        assert out["id"] == "new_friend"
        on_disk = json.loads((base / "new_friend" / "persona.json").read_text())
        assert on_disk["name"] == "New Friend"
        assert on_disk["back_ground"] == "A brand new persona."
        # Full defaulted document, not today's partial dict (D3):
        assert on_disk["triggers"] == [] and on_disk["skills"] == []
        assert on_disk["is_default"] is False
        assert "id" not in on_disk

    def test_create_collision_raises(self, svc, base):
        _seed(base, "testbot")
        with pytest.raises(PersonaExists):
            svc.create("TestBot", "again")          # slugs to "testbot"

    def test_get_injects_id_and_missing_raises(self, svc, base):
        _seed(base, "testbot")
        assert svc.get("testbot")["id"] == "testbot"
        with pytest.raises(PersonaNotFound):
            svc.get("ghost")

    def test_list_skips_corrupt_files(self, svc, base):
        _seed(base, "good")
        bad = base / "bad"
        bad.mkdir(parents=True)
        (bad / "persona.json").write_text("{nope")
        out = svc.list()
        assert [p["id"] for p in out] == ["good"]

    def test_update_missing_raises(self, svc):
        with pytest.raises(PersonaNotFound):
            svc.update("ghost", dict(VALID))

    def test_update_strips_id_and_validates(self, svc, base):
        _seed(base, "testbot")
        data = dict(VALID, id="testbot", back_ground="edited")
        out = svc.update("testbot", data)
        assert out["id"] == "testbot" and out["back_ground"] == "edited"
        on_disk = json.loads((base / "testbot" / "persona.json").read_text())
        assert "id" not in on_disk and on_disk["back_ground"] == "edited"

    def test_update_invalid_doc_leaves_file_untouched(self, svc, base):
        _seed(base, "testbot")
        with pytest.raises(ValidationError):
            svc.update("testbot", {"name": "only a name"})
        on_disk = json.loads((base / "testbot" / "persona.json").read_text())
        assert on_disk["back_ground"] == "bg"

    def test_update_preserves_animations(self, svc, base):
        # Pin for the Task-3 gap: validated writes must not drop custom clips.
        _seed(base, "testbot")
        data = dict(VALID, animations=[{"name": "wave", "url": "u.vrma"}])
        svc.update("testbot", data)
        on_disk = json.loads((base / "testbot" / "persona.json").read_text())
        assert on_disk["animations"] == [{"name": "wave", "url": "u.vrma"}]

    def test_delete_guards(self, svc, base):
        with pytest.raises(PersonaNotFound):
            svc.delete("ghost")
        _seed(base, "active_bot")
        with pytest.raises(PersonaActive):
            svc.delete("active_bot")                 # injected callable matches

    def test_delete_removes_dir_and_cached_history(self, svc, base):
        _seed(base, "doomed")
        svc.load_history("doomed")
        assert "doomed" in svc.histories
        svc.delete("doomed")
        assert not (base / "doomed").exists()
        assert "doomed" not in svc.histories         # no resurrection on re-create

    def test_get_model_returns_persona(self, svc, base):
        from persona import Persona
        _seed(base, "testbot")
        p = svc.get_model("testbot")
        assert isinstance(p, Persona) and p.name == "TestBot"
        with pytest.raises(PersonaNotFound):
            svc.get_model("ghost")


class TestHistory:
    def test_load_caps_and_caches_same_object(self, svc, base):
        d = base / "alpha"
        d.mkdir(parents=True)
        big = [{"role": "user", "content": f"m{i}"} for i in range(20)]
        (d / "chat_history.json").write_text(json.dumps(big))
        loaded = svc.load_history("alpha")
        assert len(loaded) == 5                      # history_cap=5 fixture
        assert loaded[-1] == {"role": "user", "content": "m19"}
        assert loaded is svc.histories["alpha"]      # same object: in-place
                                                     # mutation hits the cache

    def test_load_is_idempotent_and_keeps_mutations(self, svc):
        first = svc.load_history("alpha")
        first.append({"role": "user", "content": "hi"})
        assert svc.load_history("alpha") is first

    def test_save_persists_cache_and_delete_clears_both(self, svc, base):
        svc.load_history("alpha").append({"role": "user", "content": "ping"})
        svc.save_history("alpha")
        path = base / "alpha" / "chat_history.json"
        assert json.loads(path.read_text()) == [{"role": "user", "content": "ping"}]
        svc.delete_history("alpha")
        assert "alpha" not in svc.histories
        assert not path.exists()

    def test_save_unloaded_is_a_noop(self, svc, base):
        d = base / "alpha"
        d.mkdir(parents=True)
        on_disk = [{"role": "user", "content": "precious"}]
        (d / "chat_history.json").write_text(json.dumps(on_disk))
        svc.save_history("alpha")                    # never loaded: must not wipe
        assert json.loads((d / "chat_history.json").read_text()) == on_disk


class TestTriggers:
    def test_get_triggers_defaults_empty(self, svc, base):
        _seed(base, "testbot")                       # VALID has no triggers key
        assert svc.get_triggers("testbot") == []
        with pytest.raises(PersonaNotFound):
            svc.get_triggers("ghost")

    def test_replace_validates_rows_and_persists(self, svc, base):
        _seed(base, "testbot")
        trig = [{"on": {"phrase": "show camera"},
                 "do": {"skill": "show_pip", "params": {"source": "cam.1"}}}]
        out = svc.replace_triggers("testbot", trig)
        assert out[0]["on"]["phrase"] == "show camera"
        on_disk = json.loads((base / "testbot" / "persona.json").read_text())
        assert on_disk["triggers"][0]["do"]["skill"] == "show_pip"

    def test_replace_invalid_row_leaves_file_untouched(self, svc, base):
        _seed(base, "testbot")
        with pytest.raises(ValidationError):
            # TriggerOn requires phrase or event — {} is invalid.
            svc.replace_triggers("testbot", [{"on": {}, "do": {"skill": "x"}}])
        on_disk = json.loads((base / "testbot" / "persona.json").read_text())
        assert "triggers" not in on_disk or on_disk["triggers"] == []

    def test_replace_missing_persona_raises(self, svc):
        with pytest.raises(PersonaNotFound):
            svc.replace_triggers("ghost", [])
