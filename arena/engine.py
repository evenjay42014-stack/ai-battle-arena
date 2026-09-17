"""Minimal fight engine: pair fighters, score, emit bus events, snapshot."""

from __future__ import annotations

import json
import time
from itertools import combinations
from pathlib import Path
from typing import Any

from arena.agents import Fighter, build_roster
from arena.bus import ContextBus

DATA_DIR = Path(__file__).resolve().parent / "data"


def _score(a: str, b: str) -> tuple[float, float]:
    """Cheap heuristic: longer non-empty answer with more unique tokens wins slightly."""
    def pts(t: str) -> float:
        words = set(t.lower().split())
        return min(len(t), 800) * 0.01 + len(words) * 0.5

    sa, sb = pts(a), pts(b)
    if abs(sa - sb) < 0.5:
        return 0.5, 0.5
    if sa > sb:
        return 1.0, 0.0
    return 0.0, 1.0


def _elo_update(ra: float, rb: float, score_a: float, k: float = 32.0) -> tuple[float, float]:
    ea = 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))
    eb = 1.0 - ea
    return ra + k * (score_a - ea), rb + k * ((1.0 - score_a) - eb)


def fight_once(
    a: Fighter,
    b: Fighter,
    bus: ContextBus,
    *,
    prompt: str | None = None,
) -> dict[str, Any]:
    prompt = prompt or (
        "Logic Gauntlet: A says 'all cats are mammals'. B says 'some mammals fly'. "
        "Can we conclude some cats fly? Answer in one sentence, then one word: YES or NO."
    )
    battle_id = f"battle_{int(time.time() * 1000)}_{a.id}_{b.id}"
    bus.emit(
        "battle.start",
        {"id": battle_id, "a": a.id, "b": b.id, "prompt": prompt},
        actor="engine",
    )
    ans_a = a.answer(prompt)
    ans_b = b.answer(prompt)
    bus.emit(
        "battle.answers",
        {"id": battle_id, "a": ans_a[:2000], "b": ans_b[:2000]},
        actor="engine",
    )
    sa, sb = _score(ans_a, ans_b)
    a.elo, b.elo = _elo_update(a.elo, b.elo, sa)
    if sa > sb:
        a.wins += 1
        b.losses += 1
        winner = a.id
    elif sb > sa:
        b.wins += 1
        a.losses += 1
        winner = b.id
    else:
        winner = "draw"
    result = {
        "id": battle_id,
        "a": a.id,
        "b": b.id,
        "score_a": sa,
        "score_b": sb,
        "winner": winner,
        "elo_a": round(a.elo, 1),
        "elo_b": round(b.elo, 1),
        "mode_a": a.mode,
        "mode_b": b.mode,
    }
    bus.emit("battle.end", result, actor="engine")
    return result


def round_robin(
    fighters: list[Fighter] | None = None,
    *,
    bus: ContextBus | None = None,
    limit_pairs: int | None = None,
) -> dict[str, Any]:
    bus = bus or ContextBus()
    fighters = fighters or build_roster()
    bus.emit(
        "tournament.start",
        {"fighters": [f.id for f in fighters], "modes": {f.id: f.mode for f in fighters}},
        actor="engine",
    )
    pairs = list(combinations(fighters, 2))
    if limit_pairs is not None:
        pairs = pairs[:limit_pairs]
    results: list[dict[str, Any]] = []
    for a, b in pairs:
        results.append(fight_once(a, b, bus))
    standings = sorted(
        [
            {
                "id": f.id,
                "lab": f.lab,
                "mode": f.mode,
                "elo": round(f.elo, 1),
                "wins": f.wins,
                "losses": f.losses,
            }
            for f in fighters
        ],
        key=lambda r: (-r["elo"], -r["wins"], r["id"]),
    )
    snapshot = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "standings": standings,
        "battles": results,
        "event_count": len(bus.events),
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "snapshot.json"
    path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    bus.emit("tournament.end", {"snapshot": str(path), "standings": standings}, actor="engine")
    bus.dump(DATA_DIR / "bus.json")
    return snapshot


def single_fight(
    a_id: str | None = None,
    b_id: str | None = None,
    *,
    bus: ContextBus | None = None,
) -> dict[str, Any]:
    bus = bus or ContextBus()
    roster = build_roster()
    by_id = {f.id: f for f in roster}
    a = by_id.get(a_id) if a_id else roster[0]
    b = by_id.get(b_id) if b_id else roster[1]
    if a is None or b is None:
        raise ValueError("unknown fighter id")
    result = fight_once(a, b, bus)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "snapshot.json"
    path.write_text(
        json.dumps({"ts": time.time(), "last_battle": result}, indent=2),
        encoding="utf-8",
    )
    return result
