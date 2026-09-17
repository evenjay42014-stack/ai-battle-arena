"""FFA engine: _sched."""
from arena._ffa_impl.common import *  # noqa: F403
from arena._ffa_impl._elo import *  # noqa: F403
from arena._ffa_impl._judge_parse import *  # noqa: F403
from arena._ffa_impl._dual import *  # noqa: F403
from arena._ffa_impl._pbp import *  # noqa: F403
from arena._ffa_impl._fight4 import *  # noqa: F403
from arena._ffa_impl._fight1 import *  # noqa: F403
from arena._ffa_impl._merge import *  # noqa: F403

def round_robin(
    fighters: list[Fighter] | None = None,
    *,
    bus: ContextBus | None = None,
    playbook: Playbook | None = None,
    limit_pairs: int | None = None,
    limit_groups: int | None = None,
    protocols_per_pair: int = 1,
    use_all_protocols: bool = False,
    persist: bool = True,
) -> dict[str, Any]:
    """Learning-optimized FFA tournament with hole curriculum + persisted playbook."""
    bus = bus or ContextBus()
    playbook = playbook or Playbook.load_or_new()
    fighters = fighters or build_roster()
    start_elo = {f.id: f.elo for f in fighters}
    start_rules = len(playbook.rules)
    start_lessons = len(playbook.lessons)

    # limit_pairs kept as alias for limit_groups for CLI compat
    if limit_groups is None and limit_pairs is not None:
        limit_groups = limit_pairs

    bus.emit(
        "tournament.start",
        {
            "fighters": [f.id for f in fighters],
            "modes": {f.id: f.mode for f in fighters},
            "format": "ffa4",
            "protocols": [p.id for p in PROTOCOLS],
            "playbook_rules_loaded": start_rules,
            "playbook_lessons_loaded": start_lessons,
        },
        actor="engine",
    )

    if use_all_protocols:
        groups = [list(g) for g in combinations(fighters, 4)]
        if limit_groups is not None:
            groups = groups[:limit_groups]
        schedule = [(g, proto, True) for g in groups for proto in PROTOCOLS]
    else:
        schedule = build_learning_schedule(
            fighters, limit_groups=limit_groups, ensure_all_protocols=True
        )
        if protocols_per_pair > 1:
            # Extra hard drills cycling protocols
            extra: list[tuple[list[Fighter], Protocol, bool]] = []
            groups = [list(g) for g in combinations(fighters, 4)]
            if limit_groups is not None:
                groups = groups[:limit_groups]
            i = 0
            for g in groups:
                for _ in range(protocols_per_pair - 1):
                    proto = protocol_at(i)
                    extra.append((g, proto, True))
                    i += 1
            schedule.extend(extra)

    results: list[dict[str, Any]] = []
    api_failures = 0
    for battle_i, (group, proto, hard) in enumerate(schedule):
        result = fight_four(
            group,
            bus,
            protocol=proto,
            playbook=playbook,
            battle_index=battle_i,
            hard=True,  # default hard for scheduled fights
        )
        results.append(result)
        append_battle_history(result)
        print(
            f"  [{battle_i + 1}/{len(schedule)}] {proto.name}*FFA: "
            f"{'/'.join(f.id for f in group)} → {result['winner']} "
            f"lessons+={len(result['lessons'])} rules={result['playbook_rules_after']} "
            f"({result['judge']})",
            flush=True,
        )

    for ev in bus.of_type("battle.answers"):
        payload = ev.payload
        if "answers" in payload:
            for v in (payload.get("answers") or {}).values():
                if "live call failed" in str(v).lower() or str(v).startswith("[LIVE ERROR]"):
                    api_failures += 1
        else:
            for key in ("a", "b"):
                if "live call failed" in str(payload.get(key, "")):
                    api_failures += 1

    standings = sorted(
        [
            {
                "id": f.id,
                "lab": f.lab,
                "mode": f.mode,
                "elo": round(f.elo, 1),
                "elo_delta": round(f.elo - start_elo[f.id], 1),
                "wins": f.wins,
                "losses": f.losses,
                "spike": f.spike,
                "hole": f.hole,
            }
            for f in fighters
        ],
        key=lambda r: (-r["elo"], -r["wins"], r["id"]),
    )

    lessons_created = playbook.lessons_created_session
    playbook_size = len(playbook.rules)
    promoted = sum(1 for r in playbook.rules if r.promoted)
    improvement_signals = {
        "elo_movers": sorted(
            [{"id": s["id"], "elo_delta": s["elo_delta"]} for s in standings],
            key=lambda x: -abs(x["elo_delta"]),
        )[:6],
        "rules_added": playbook_size - start_rules,
        "promoted_total": promoted,
        "hole_protocol_fights": sum(1 for r in results if r.get("hard")),
        "avg_lessons_per_battle": round(
            (sum(len(r.get("lessons") or []) for r in results) / max(1, len(results))), 2
        ),
        "judge_disagreements": sum(
            1 for r in results if (r.get("disagreement") or {}).get("winner_mismatch")
        ),
    }

    if persist:
        playbook.save()

    snapshot = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "standings": standings,
        "battles": results,
        "playbook": playbook.to_dict(),
        "lessons": [L.to_dict() for L in playbook.lessons[-100:]],
        "lessons_created": lessons_created,
        "playbook_size": playbook_size,
        "improvement_signals": improvement_signals,
        "protocols_used": sorted({r["protocol"] for r in results}),
        "event_count": len(bus.events),
        "api_failures": api_failures,
        "judge_live_count": sum(1 for r in results if r.get("judge_live")),
        "judge_fallback_count": sum(1 for r in results if not r.get("judge_live")),
        "format": "ffa4",
        "_elo_baseline": start_elo,
    }
    path = _write_snapshot(snapshot)
    bus.emit(
        "tournament.end",
        {
            "snapshot": str(path),
            "standings": standings,
            "lessons_created": lessons_created,
            "playbook_size": playbook_size,
        },
        actor="engine",
    )
    bus.dump(DATA_DIR / "bus.json")
    return snapshot


def single_fight(
    a_id: str | None = None,
    b_id: str | None = None,
    *,
    bus: ContextBus | None = None,
    protocol_id: str | None = None,
    prompt: str | None = None,
    fighter_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Run one FFA (preferred) or legacy pair if only 2 ids given."""
    bus = bus or ContextBus()
    playbook = Playbook.load_or_new()
    roster = build_roster()
    by_id = {f.id: f for f in roster}

    proto = PROTOCOL_BY_ID.get(protocol_id) if protocol_id else None

    if fighter_ids and len(fighter_ids) >= 4:
        group = [by_id[i] for i in fighter_ids[:4] if i in by_id]
    elif a_id and b_id:
        # Build FFA around the requested pair
        rest = [f for f in roster if f.id not in (a_id, b_id)]
        group = [by_id[a_id], by_id[b_id]] + rest[:2]
    else:
        group = roster[:4]

    if len(group) < 4:
        raise ValueError("need 4 fighters")

    result = fight_four(
        group,
        bus,
        protocol=proto,
        playbook=playbook,
        hard=True,
        custom_prompt=prompt,
    )
    playbook.save()
    merge_battle_into_snapshot(result, roster, playbook, bus=bus)
    return result

__all__ = ['round_robin', 'single_fight']
