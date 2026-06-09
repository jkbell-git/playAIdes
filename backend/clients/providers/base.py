"""The provider seam — deliberately small so HA's needs shape it without over-fitting.

A provider connects one external service, reports its health, discovers the
entities it exposes (normalized), and invokes a capability against a target.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

# playAIdes capability keys — generic, provider-agnostic. A discovered Item advertises
# which of these it can fill. Most map to a single (provider, entity); `pip` is a generic
# display slot whose mapping is a typed source — {kind:"camera", provider, entity} or
# {kind:"url", url} — so a camera is just one PiP source among others.
CAP_PIP = "pip"
CAP_SAY_TARGET = "say_target"
CAP_LAUNCH_TARGETS = "launch_targets"
CAP_SCRIPTS = "scripts"


@dataclass
class Status:
    ok: bool
    reason: Optional[str] = None  # human-readable failure reason; None when ok


@dataclass
class Item:
    """A normalized, discovered entity."""
    id: str                       # provider-native id, e.g. "camera.front_door"
    domain: str                   # grouping key, e.g. "camera"
    name: str                     # friendly name
    capabilities: list[str] = field(default_factory=list)  # caps it can fill


class Provider(ABC):
    kind: str                     # e.g. "homeassistant"
    config_schema: list[str] = [] # non-secret config fields needed to connect

    @abstractmethod
    def health(self) -> Status: ...

    @abstractmethod
    def discover(self) -> list[Item]: ...

    @abstractmethod
    def invoke(self, capability: str, target: str, args: Optional[dict] = None) -> dict: ...
