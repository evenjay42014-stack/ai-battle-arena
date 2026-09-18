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


def _recent_fighter_counts(battles: list[dict[str, Any]], window: int = 24) -> dict[str, int]:
    """How often each fighter appeared in the recent battle window."""
    counts: dict[str, int] = {}
    for b in (battles or [])[-window:]:
        ids = b.get("fighters")
        if not ids:
            ids = [b.get("a"), b.get("b"), b.get("c"), b.get("d")]
        for fid in ids:
            if not fid:
                continue
            counts[str(fid)] = counts.get(str(fid), 0) + 1
    return counts


def _pick_rotated_fighters(roster: list[Fighter], prev: dict[str, Any], n: int = 4) -> list[Fighter]:
    """Pick n fighters with fair rotation so the same subset is not reused every fight.

    With a 6-fighter roster and n=4, two fighters sit out each battle. The sit-out
    window advances each battle so every fighter sits out equally over time.
    Within the active set we still prefer provider diversity when breaking ties.
    """
    if len(roster) <= n:
        return list(roster)

    battles = list(prev.get("battles") or [])
    ordered_ids = sorted(f.id for f in roster)
    by_id = {f.id: f for f in roster}
    sit = len(roster) - n
    # Advance sit-out window by `sit` each battle for even coverage
    start = (len(battles) * sit) % len(roster)
    sit_ids = {ordered_ids[(start + i) % len(roster)] for i in range(sit)}
    active = [by_id[i] for i in ordered_ids if i not in sit_ids]

    # Soft provider diversity within the rotated active set (stable order)
    recent = _recent_fighter_counts(battles)
    active.sort(key=lambda f: (recent.get(f.id, 0), f.wins + f.losses, -f.elo, f.id))
    chosen: list[Fighter] = []
    used_providers: set[str] = set()
    for f in active:
        if f.provider in used_providers:
            continue
        chosen.append(f)
        used_providers.add(f.provider)
    for f in active:
        if f in chosen:
            continue
        chosen.append(f)
        if len(chosen) >= n:
            break
    return chosen[:n]


def _hardest_protocol(protocol_id: str | None, battle_count: int) -> Protocol:
    """Resolve protocol for empty-prompt fights: explicit id, else rotate hardest suite."""
    if protocol_id and protocol_id in PROTOCOL_BY_ID:
        return PROTOCOL_BY_ID[protocol_id]
    # Rotate through all protocols so empty-prompt fights stay adversarial and varied
    return protocol_at(battle_count)


def run_custom_battle(
    prompt: str | None = None,
    *,
    protocol_id: str | None = None,
    fighter_ids: list[str] | None = None,
    hard: bool = True,
    prefer_live: bool = True,
) -> dict[str, Any]:
    """Run one 4-fighter FFA. Empty prompt → hardest protocol generator; rotates fighters."""
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
        if len(chosen) < 4:
            for f in _pick_rotated_fighters(roster, prev, n=4):
                if f not in chosen:
                    chosen.append(f)
                if len(chosen) == 4:
                    break
    else:
        chosen = _pick_rotated_fighters(roster, prev, n=4)

    if len(chosen) != 4:
        raise ValueError("need 4 fighters in roster")

    battles = list(prev.get("battles") or [])
    proto = _hardest_protocol(protocol_id, len(battles))
    user_prompt = (prompt or "").strip()
    # Empty bar → protocol's hardest generated challenge (no soft custom text)
    custom = user_prompt if user_prompt else None
    hard = True if not user_prompt else bool(hard)

    result = fight_four(
        chosen,
        bus,
        protocol=proto,
        playbook=playbook,
        hard=hard,
        custom_prompt=custom,
    )
    playbook.save()
    snapshot = merge_battle_into_snapshot(result, roster, playbook, bus=bus)
    bus.dump(DATA_DIR / "bus.json")
    return {"battle": result, "snapshot": snapshot}

__all__ = ['merge_battle_into_snapshot', 'run_custom_battle', '_pick_rotated_fighters', '_hardest_protocol', '_recent_fighter_counts']
