"""Append-only context bus. This is how every AI stays connected."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable


def _ulid() -> str:
    return uuid.uuid4().hex[:16]


@dataclass
class Event:
    type: str
    actor: str
    payload: dict[str, Any]
    visibility: str = "public"
    corr: dict[str, str] = field(default_factory=dict)
    id: str = field(default_factory=lambda: f"evt_{_ulid()}")
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.ts))
        return d


class ContextBus:
    def __init__(self) -> None:
        self.events: list[Event] = []
        self._subs: list[Callable[[Event], None]] = []

    def subscribe(self, fn: Callable[[Event], None]) -> None:
        self._subs.append(fn)

    def emit(
        self,
        type: str,
        payload: dict | None = None,
        *,
        actor: str = "system",
        visibility: str = "public",
        corr: dict | None = None,
    ) -> Event:
        ev = Event(type=type, actor=actor, payload=payload or {}, visibility=visibility, corr=corr or {})
        self.events.append(ev)
        for fn in self._subs:
            fn(ev)
        return ev

    def of_type(self, type: str) -> list[Event]:
        return [e for e in self.events if e.type == type]

    def dump(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps([e.to_dict() for e in self.events], indent=2), encoding="utf-8")
