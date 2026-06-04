import sys
import types
from unittest.mock import MagicMock

# Stub out unavailable native deps so PlayAIdes can be imported without
# the full Docker environment.
for _mod in ("voicebox_client", "voicebox", "voicebox.api_models", "incarnation_server", "ha_client"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

from skills.registry import SkillRegistry
from skills.pip import ShowPipSkill


def _make_ai():
    from playAIdes import PlayAIdes
    ai = PlayAIdes.__new__(PlayAIdes)
    ai.incarnation_server = MagicMock()
    ai.args = types.SimpleNamespace(use_voice=False, use_avatar=False)
    ai.current_persona = types.SimpleNamespace(name="Silver", persona_voice=None, language="English")
    reg = SkillRegistry()
    reg.register(ShowPipSkill())
    ai.skill_registry = reg
    return ai


def test_dispatch_skill_runs_skill_and_sends_ws():
    ai = _make_ai()
    ai._dispatch_skill("silver", "show_pip", {"url": "http://x/stream", "kind": "live"})
    ai.incarnation_server.broadcast_to_persona.assert_any_call(
        "silver", "show_pip",
        {"url": "http://x/stream", "kind": "live", "dismiss": {"type": "until_dismissed"}},
    )


def test_dispatch_unknown_skill_is_noop():
    ai = _make_ai()
    ai._dispatch_skill("silver", "nope", {})       # must not raise
    ai.incarnation_server.broadcast_to_persona.assert_not_called()


def test_dispatch_bad_params_is_noop():
    ai = _make_ai()
    ai._dispatch_skill("silver", "show_pip", {})    # missing required `url`; must not raise
    ai.incarnation_server.broadcast_to_persona.assert_not_called()
