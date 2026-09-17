"""FFA engine: _fight1."""
from arena._ffa_impl.common import *  # noqa: F403
from arena._ffa_impl._elo import *  # noqa: F403
from arena._ffa_impl._judge_parse import *  # noqa: F403
from arena._ffa_impl._dual import *  # noqa: F403
from arena._ffa_impl._pbp import *  # noqa: F403
from arena._ffa_impl._fight4 import *  # noqa: F403

def fight_once(
    a: Fighter,
    b: Fighter,
    bus: ContextBus,
    *,
    protocol: Protocol | None = None,
    playbook: Playbook | None = None,
    prompt: str | None = None,
    battle_index: int = 0,
    hard: bool = True,
) -> dict[str, Any]:
    """Legacy 1v1 path — dual-judge wrapper keeping a/b result shape."""
    protocol = protocol or protocol_at(battle_index)
    playbook = playbook or Playbook()
    hard = hard or (a.hole == protocol.axis or b.hole == protocol.axis)
    prompt = prompt or protocol.prompt_for(a.id, b.id, salt=str(battle_index), hard=hard)
    battle_id = f"battle_{int(time.time() * 1000)}_{a.id}_{b.id}_{protocol.id}"

    bus.emit(
        "battle.start",
        {
            "id": battle_id,
            "a": a.id,
            "b": b.id,
            "protocol": protocol.id,
            "axis": protocol.axis,
            "hard": hard,
            "prompt": prompt,
        },
        actor="engine",
    )

    ctx_a = playbook.context_for(a.id)
    ctx_b = playbook.context_for(b.id)
    ans_a = a.answer(prompt, playbook_context=ctx_a or None, system=protocol.system)
    ans_b = b.answer(prompt, playbook_context=ctx_b or None, system=protocol.system)
    bus.emit(
        "battle.answers",
        {"id": battle_id, "a": ans_a[:2000], "b": ans_b[:2000]},
        actor="engine",
    )

    answers = {a.id: ans_a, b.id: ans_b}
    judgment = dual_judge(
        prompt, answers, protocol, exclude_providers=list({a.provider, b.provider})
    )
    ranking = judgment["combined_ranking"]
    # Map to sa/sb for elo
    if ranking[0] == a.id:
        sa, sb = 1.0, 0.0
    elif ranking[0] == b.id:
        sa, sb = 0.0, 1.0
    else:
        sa, sb = 0.5, 0.5

    elo_a_before, elo_b_before = a.elo, b.elo
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

    lessons = _emit_ffa_lessons(
        fighters=[a, b],
        answers=answers,
        ranking=ranking,
        protocol=protocol,
        battle_id=battle_id,
        playbook=playbook,
        bus=bus,
        disagreement=judgment["disagreement"],
    )
    play_by_play = _build_play_by_play(
        prompt=prompt,
        fighters=[a, b],
        answers=answers,
        judgment=judgment,
        lessons=lessons,
        winner=winner,
    )

    result = {
        "id": battle_id,
        "format": "1v1",
        "fighters": [a.id, b.id],
        "a": a.id,
        "b": b.id,
        "protocol": protocol.id,
        "protocol_name": protocol.name,
        "axis": protocol.axis,
        "hard": hard,
        "score_a": sa,
        "score_b": sb,
        "ranking": ranking,
        "winner": winner,
        "elo_a": round(a.elo, 1),
        "elo_b": round(b.elo, 1),
        "elo_delta_a": round(a.elo - elo_a_before, 1),
        "elo_delta_b": round(b.elo - elo_b_before, 1),
        "mode_a": a.mode,
        "mode_b": b.mode,
        "judges": {"judge1": judgment["judge1"], "judge2": judgment["judge2"]},
        "disagreement": judgment["disagreement"],
        "judge": f"dual j1={judgment['judge1']['note']} | j2={judgment['judge2']['note']}",
        "judge_live": judgment["any_live"],
        "lessons": lessons,
        "playbook_rules_after": len(playbook.rules),
        "prompt": prompt[:800],
        "play_by_play": play_by_play,
    }
    bus.emit("battle.end", result, actor="engine")
    return result


def build_learning_schedule(
    fighters: list[Fighter],
    *,
    limit_groups: int | None = None,
    ensure_all_protocols: bool = True,
    extra_hole_drills: int = 2,
) -> list[tuple[list[Fighter], Protocol, bool]]:
    """Curriculum of 4-fighter groups × protocols. hard=True by default."""
    if len(fighters) < 4:
        raise ValueError("need at least 4 fighters for FFA schedule")
    groups = [list(g) for g in combinations(fighters, 4)]
    if limit_groups is not None:
        groups = groups[:limit_groups]

    schedule: list[tuple[list[Fighter], Protocol, bool]] = []
    hole_hits: dict[str, int] = {f.id: 0 for f in fighters}
    fight_counts: dict[str, int] = {f.id: 0 for f in fighters}

    def best_group_for(proto: Protocol) -> tuple[list[Fighter], bool] | None:
        best: tuple[list[Fighter], int, bool] | None = None
        for g in groups:
            score = 0
            hard = True
            for f in g:
                if f.hole == proto.axis:
                    score += 4
                if f.spike == proto.axis:
                    score += 1
                score -= fight_counts[f.id]
                score -= hole_hits[f.id]
            if best is None or score > best[1]:
                best = (g, score, hard)
        if best is None:
            return None
        return best[0], best[2]

    if ensure_all_protocols:
        for proto in PROTOCOLS:
            picked = best_group_for(proto)
            if not picked:
                continue
            g, hard = picked
            schedule.append((g, proto, True))  # always hard
            for f in g:
                fight_counts[f.id] += 1
                if f.hole == proto.axis:
                    hole_hits[f.id] += 1

    drills = 0
    while drills < extra_hole_drills and fighters:
        target = min(fighters, key=lambda f: (hole_hits[f.id], fight_counts[f.id]))
        cands = protocols_for_hole(target.hole)
        if not cands:
            break
        proto = cands[drills % len(cands)]
        # Build group: target + 3 others (prefer spike match / least fought)
        others = [f for f in fighters if f.id != target.id]
        others.sort(
            key=lambda f: (0 if f.spike == proto.axis else 1, fight_counts[f.id])
        )
        g = [target] + others[:3]
        if len(g) < 4:
            break
        schedule.append((g, proto, True))
        for f in g:
            fight_counts[f.id] += 1
        hole_hits[target.id] += 1
        drills += 1

    return schedule


def append_battle_history(result: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")


def _load_snapshot() -> dict[str, Any]:
    path = DATA_DIR / "snapshot.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _write_snapshot(snapshot: dict[str, Any]) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "snapshot.json"
    path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    return path

__all__ = ['fight_once', 'build_learning_schedule', 'append_battle_history', '_load_snapshot', '_write_snapshot']
