from persona import Persona, Trigger


def _base_persona_kwargs():
    return {
        "name": "Silver",
        "back_ground": "bg",
        "psyche": {"traits": ["loyal"]},
        "gender": "Female",
    }


def test_persona_defaults_have_empty_skills_and_triggers():
    p = Persona(**_base_persona_kwargs())
    assert p.skills == []
    assert p.triggers == []


def test_persona_parses_phrase_and_event_triggers():
    p = Persona(
        **_base_persona_kwargs(),
        skills=["show_pip", "dismiss_pip"],
        triggers=[
            {"on": {"phrase": "show the front door"},
             "do": {"skill": "show_pip", "params": {"url": "http://x/stream", "kind": "live"}}},
            {"on": {"event": "front_door_motion", "match": {"state": "on"}},
             "do": {"skill": "show_pip"}},
        ],
    )
    assert p.skills == ["show_pip", "dismiss_pip"]
    assert isinstance(p.triggers[0], Trigger)
    assert p.triggers[0].on.phrase == "show the front door"
    assert p.triggers[0].do.skill == "show_pip"
    assert p.triggers[0].do.params == {"url": "http://x/stream", "kind": "live"}
    assert p.triggers[1].on.event == "front_door_motion"
    assert p.triggers[1].do.params == {}


def test_existing_persona_json_without_skills_still_loads():
    # Back-compat: omitting the new fields must not break.
    p = Persona(**_base_persona_kwargs())
    assert isinstance(p, Persona)
