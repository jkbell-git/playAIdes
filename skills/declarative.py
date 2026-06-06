# skills/declarative.py
"""Declarative skill kinds — bash (argv) and http (request), built from pack
specs (spec §3.2). These are Skill *instances* whose `name` and `Params` come
from the spec at load time, so the registry treats them like internal skills.

Security: bash runs an argv array with shell=False — params are substituted as
discrete argv elements, never concatenated into a shell, so no user value can
reach a shell. http percent-encodes url values and JSON-encodes body values.
"""
from __future__ import annotations

import logging
import subprocess
import urllib.parse
from typing import Any

import httpx
from pydantic import BaseModel, create_model

from skills.base import Skill, SkillContext, SkillResult

logger = logging.getLogger(__name__)

_TYPE_MAP = {"str": str, "int": int, "float": float, "bool": bool}


def build_params_model(skill_name: str, params_spec: dict) -> type[BaseModel]:
    """Build a Pydantic model from a {param_name: type_string} spec. All declared
    params are required. Unknown type strings fail-fast (raise ValueError)."""
    fields: dict[str, tuple] = {}
    for pname, type_str in (params_spec or {}).items():
        if type_str not in _TYPE_MAP:
            raise ValueError(
                f"skill {skill_name!r}: param {pname!r} has unknown type {type_str!r} "
                f"(allowed: {sorted(_TYPE_MAP)})"
            )
        fields[pname] = (_TYPE_MAP[type_str], ...)
    return create_model(f"{skill_name}_Params", **fields)


class BashSkill(Skill):
    # Class-level placeholders satisfy Skill.__init_subclass__ (which requires a
    # str `name` and a `Params` attr at subclass-definition time). The real
    # per-instance name/Params are set in __init__ from the pack spec.
    name = "bash"
    kind = "bash"
    Params = BaseModel

    def __init__(self, spec: dict) -> None:
        self.name = spec["name"]
        self.kind = "bash"
        self.command: list[str] = list(spec["command"])
        if not self.command:
            raise ValueError(f"bash skill {self.name!r}: 'command' must be a non-empty argv list")
        if not all(isinstance(p, str) for p in self.command):
            raise ValueError(f"bash skill {self.name!r}: 'command' elements must all be strings")
        self.timeout_s: float = float(spec.get("timeout_s", 10))
        self.announce_output: bool = bool(spec.get("announce_output", False))
        self.Params = build_params_model(self.name, spec.get("params", {}))

    def execute(self, params: BaseModel, ctx: SkillContext) -> SkillResult:
        values = params.model_dump()
        try:
            # Per-element .format on the argv template; values are inserted as
            # whole, discrete argv elements (shell=False below) — no injection.
            argv = [part.format(**values) for part in self.command]
        except (KeyError, IndexError, ValueError) as e:
            logger.warning("bash skill %r: template references unknown param: %s", self.name, e)
            return SkillResult(ok=False, error=f"bad template: {e}")
        try:
            proc = subprocess.run(
                argv, capture_output=True, text=True,
                timeout=self.timeout_s, shell=False,
            )
        except subprocess.TimeoutExpired:
            logger.warning("bash skill %r timed out after %ss", self.name, self.timeout_s)
            return SkillResult(ok=False, error="timeout")
        except Exception as e:
            logger.exception("bash skill %r failed to run", self.name)
            return SkillResult(ok=False, error=str(e))
        out = (proc.stdout or "").strip()
        if self.announce_output and out:
            ctx.speak(out)
        return SkillResult(
            ok=(proc.returncode == 0),
            output=out or None,
            error=((proc.stderr or "").strip() or None) if proc.returncode != 0 else None,
        )


def _interpolate_body(template: Any, values: dict) -> Any:
    """Deep-substitute into a JSON body template. A string of the exact form
    '{pname}' becomes the raw (typed) value so ints/bools survive JSON encoding;
    other strings go through str.format; dicts/lists recurse. httpx JSON-encodes
    the result, so no manual escaping is needed."""
    if isinstance(template, str):
        if template.startswith("{") and template.endswith("}") and template[1:-1] in values:
            return values[template[1:-1]]
        try:
            return template.format(**values)
        except (KeyError, IndexError, ValueError):
            return template
    if isinstance(template, dict):
        return {k: _interpolate_body(v, values) for k, v in template.items()}
    if isinstance(template, list):
        return [_interpolate_body(v, values) for v in template]
    return template


class HttpSkill(Skill):
    name = "http"          # class-level placeholder (see BashSkill note)
    kind = "http"
    Params = BaseModel

    def __init__(self, spec: dict) -> None:
        self.name = spec["name"]
        self.kind = "http"
        self.method: str = str(spec.get("method", "GET")).upper()
        self.url: str = spec["url"]
        self.headers: dict = dict(spec.get("headers", {}) or {})
        self.body: Any = spec.get("body")          # dict/list template or None
        self.timeout_s: float = float(spec.get("timeout_s", 10))
        self.announce_output: bool = bool(spec.get("announce_output", False))
        self.Params = build_params_model(self.name, spec.get("params", {}))

    def execute(self, params: BaseModel, ctx: SkillContext) -> SkillResult:
        values = params.model_dump()
        try:
            # URL values percent-encoded before interpolation (no raw concat).
            enc = {k: urllib.parse.quote(str(v), safe="") for k, v in values.items()}
            url = self.url.format(**enc)
            headers = {k: str(v).format(**values) for k, v in self.headers.items()}
        except (KeyError, IndexError, ValueError) as e:
            logger.warning("http skill %r: template references unknown param: %s", self.name, e)
            return SkillResult(ok=False, error=f"bad template: {e}")
        json_body = _interpolate_body(self.body, values) if self.body is not None else None
        try:
            with httpx.Client(timeout=self.timeout_s) as client:
                resp = client.request(self.method, url, headers=headers, json=json_body)
        except Exception as e:
            logger.warning("http skill %r request failed: %s", self.name, e)
            return SkillResult(ok=False, error=str(e))
        out = (resp.text or "")[:500] or None
        if self.announce_output and out:
            ctx.speak(out)
        return SkillResult(
            ok=resp.is_success,
            output=out,
            error=None if resp.is_success else f"http_{resp.status_code}",
        )
