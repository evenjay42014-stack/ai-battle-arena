"""FFA engine: _fight4."""
from arena._ffa_impl.common import *  # noqa: F403
from arena._ffa_impl._elo import *  # noqa: F403
from arena._ffa_impl._judge_parse import *  # noqa: F403
from arena._ffa_impl._dual import *  # noqa: F403
from arena._ffa_impl._pbp import *  # noqa: F403

def fight_four(
    fighters: Sequence[Fighter],
    bus: ContextBus,
    *,
    protocol: Protocol | None = None,
    playbook: Playbook | None = None,
    prompt: str | None = None,
    battle_index: int = 0,
    hard: bool = True,
    custom_prompt: str | None = None,
) -> dict[str, Any]:
    """4-fighter free-for-all with dual judges and play-by-play timeline."""
    fighters = list(fighters)
    if len(fighters) != 4:
        raise ValueError(f"fight_four requires exactly 4 fighters, got {len(fighters)}")
    protocol = protocol or protocol_at(battle_index)
    playbook = playbook or Playbook()
    hard = True if hard is None else bool(hard)
    # Hole stress still forces hard
    if any(f.hole == protocol.axis for f in fighters):
        hard = True

    ids = [f.id for f in fighters]
    if custom_prompt:
        prompt = protocol.prompt_for(
            fighter_ids=ids, salt=str(battle_index), hard=hard, custom_prompt=custom_prompt
        )
    else:
        prompt = prompt or protocol.prompt_for(
            fighter_ids=ids, salt=str(battle_index), hard=hard
        )

    battle_id = f"battle_{int(time.time() * 1000)}_{'_'.join(ids[:2])}_{protocol.id}_ffa"

    bus.emit(
        "battle.start",
        {
            "id": battle_id,
            "fighters": ids,
            "format": "ffa4",
            "protocol": protocol.id,
            "axis": protocol.axis,
            "hard": hard,
            "prompt": prompt,
        },
        actor="engine",
    )

    answers: dict[str, str] = {}
    for f in fighters:
        ctx = playbook.context_for(f.id)
        answers[f.id] = f.answer(prompt, playbook_context=ctx or None, system=protocol.system)

    bus.emit(
        "battle.answers",
        {"id": battle_id, "answers": {k: v[:2000] for k, v in answers.items()}},
        actor="engine",
    )

    exclude = list({f.provider for f in fighters})
    judgment = dual_judge(prompt, answers, protocol, exclude_providers=exclude)
    ranking = judgment["combined_ranking"]
    rank_scores = judgment["rank_scores"]

    elo_before = {f.id: f.elo for f in fighters}
    ratings = [f.elo for f in fighters]
    score_list = [rank_scores[f.id] for f in fighters]
    new_ratings = _elo_update_multi(ratings, score_list)
    for f, nr in zip(fighters, new_ratings):
        f.elo = nr

    winner = ranking[0] if ranking else "draw"
    # W-L: win = 1st place only
    for f in fighters:
        if f.id == winner:
            f.wins += 1
        else:
            f.losses += 1

    lessons = _emit_ffa_lessons(
        fighters=fighters,
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
        fighters=fighters,
        answers=answers,
        judgment=judgment,
        lessons=lessons,
        winner=winner,
    )

    result: dict[str, Any] = {
        "id": battle_id,
        "format": "ffa4",
        "fighters": ids,
        "a": ids[0],  # legacy fields for older UI
        "b": ids[1],
        "c": ids[2],
        "d": ids[3],
        "protocol": protocol.id,
        "protocol_name": protocol.name,
        "axis": protocol.axis,
        "hard": hard,
        "ranking": ranking,
        "rank_scores": {k: round(v, 3) for k, v in rank_scores.items()},
        "winner": winner,
        "elo": {f.id: round(f.elo, 1) for f in fighters},
        "elo_delta": {f.id: round(f.elo - elo_before[f.id], 1) for f in fighters},
        "modes": {f.id: f.mode for f in fighters},
        "judges": {
            "judge1": judgment["judge1"],
            "judge2": judgment["judge2"],
        },
        "disagreement": judgment["disagreement"],
        "judge_live": judgment["any_live"],
        "judge": (
            f"dual j1={judgment['judge1']['note']} | j2={judgment['judge2']['note']}"
        ),
        "lessons": lessons,
        "playbook_rules_after": len(playbook.rules),
        "prompt": prompt[:800],
        "answers": {k: v[:2000] for k, v in answers.items()},
        "play_by_play": play_by_play,
    }
    bus.emit("battle.end", {k: result[k] for k in result if k != "answers"}, actor="engine")
    return result

__all__ = ['fight_four']
