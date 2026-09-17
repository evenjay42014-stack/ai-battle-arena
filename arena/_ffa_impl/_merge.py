"""FFA engine: _merge."""
from arena._ffa_impl.common import *  # noqa: F403
from arena._ffa_impl._elo import *  # noqa: F403
from arena._ffa_impl._judge_parse import *  # noqa: F403
from arena._ffa_impl._dual import *  # noqa: F403
from arena._ffa_impl._pbp import *  # noqa: F403
from arena._ffa_impl._fight4 import *  # noqa: F403
from arena._ffa_impl._fight1 import *  # noqa: F403

def merge_battle_into_snapshot(
    result: dict[str, Any],
    fighters: list[Fighter],
    playbook: Playbook,
    *,
    bus: ContextBus | None = None,
) -> dict[str, Any]:
    """Update snapshot with one FFA battle + current standings."""
    prev = _load_snapshot()
    battles = list(prev.get("battles") or [])
    battles.append(result)
    # Keep last 40 battles in snapshot
    battles = battles[-40:]

    standings = sorted(
        [
            {
                "id": f.id,
                "lab": f.lab,
                "mode": f.mode,
                "elo": round(f.elo, 1),
                "elo_delta": round(
                    f.elo - float((prev.get("_elo_baseline") or {}).get(f.id, f.elo)),
                    1,
                ),
                "wins": f.wins,
                "losses": f.losses,
                "spike": f.spike,
                "hole": f.hole,
            }
            for f in fighters
        ],
        key=lambda r: (-r["elo"], -r["wins"], r["id"]),
    )

    snapshot = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "standings": standings,
        "battles": battles,
        "last_battle": result,
        "playbook": playbook.to_dict(),
        "lessons": [L.to_dict() for L in playbook.lessons[-100:]],
        "lessons_created": playbook.lessons_created_session,
        "playbook_size": len(playbook.rules),
        "protocols_used": sorted({r.get("protocol") for r in battles if r.get("protocol")}),
        "event_count": len(bus.events) if bus else prev.get("event_count", 0),
        "judge_live_count": sum(1 for r in battles if r.get("judge_live")),
        "judge_fallback_count": sum(1 for r in battles if not r.get("judge_live")),
        "format": "ffa4",
        "improvement_signals": prev.get("improvement_signals") or {},
        "api_failures": prev.get("api_failures", 0),
    }
    _write_snapshot(snapshot)
    append_battle_history(result)
    return snapshot


def run_custom_battle(
    prompt: str,
    *,
    protocol_id: str | None = None,
    fighter_ids: list[str] | None = None,
    hard: bool = True,
    prefer_live: bool = True,
) -> dict[str, Any]:
    """Run one 4-fighter FFA with a custom user prompt; persist snapshot + history."""
    bus = ContextBus()
    playbook = Playbook.load_or_new()
    roster = build_roster(prefer_live=prefer_live)
    by_id = {f.id: f for f in roster}

    # Restore elo/wins from snapshot if present
    prev = _load_snapshot()
    for row in prev.get("standings") or []:
        f = by_id.get(row.get("id", ""))
        if f:
            f.elo = float(row.get("elo", f.elo))
            f.wins = int(row.get("wins", f.wins))
            f.losses = int(row.get("losses", f.losses))

    if fighter_ids:
        chosen = [by_id[i] for i in fighter_ids if i in by_id]
    else:
        # Prefer diverse providers; take top-4 by least fights then elo
        chosen = sorted(roster, key=lambda f: (f.wins + f.losses, -f.elo))[:4]
        if len(chosen) < 4:
            chosen = roster[:4]

    if len(chosen) < 4:
        # pad from roster
        for f in roster:
            if f not in chosen:
                chosen.append(f)
            if len(chosen) == 4:
                break
    if len(chosen) != 4:
        raise ValueError("need 4 fighters in roster")

    proto = PROTOCOL_BY_ID.get(protocol_id) if protocol_id else protocol_at(int(time.time()) % 10)
    if proto is None:
        proto = protocol_at(0)

    result = fight_four(
        chosen,
        bus,
        protocol=proto,
        playbook=playbook,
        hard=hard,
        custom_prompt=prompt,
    )
    playbook.save()
    snapshot = merge_battle_into_snapshot(result, roster, playbook, bus=bus)
    bus.dump(DATA_DIR / "bus.json")
    return {"battle": result, "snapshot": snapshot}

__all__ = ['merge_battle_into_snapshot', 'run_custom_battle']
