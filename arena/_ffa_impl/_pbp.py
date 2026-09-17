"""FFA engine: _pbp."""
from arena._ffa_impl.common import *  # noqa: F403
from arena._ffa_impl._elo import *  # noqa: F403
from arena._ffa_impl._judge_parse import *  # noqa: F403
from arena._ffa_impl._dual import *  # noqa: F403

def _emit_ffa_lessons(
    *,
    fighters: list[Fighter],
    answers: dict[str, str],
    ranking: list[str],
    protocol: Protocol,
    battle_id: str,
    playbook: Playbook,
    bus: ContextBus,
    disagreement: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    by_id = {f.id: f for f in fighters}
    winner_id = ranking[0] if ranking else ""
    winner_ans = answers.get(winner_id, "")

    def add(
        fighter: Fighter,
        opponent: Fighter,
        answer: str,
        better: str,
        conf: float,
        role: str,
        hint: str = "",
    ) -> None:
        card = compact_lesson(
            fighter_id=fighter.id,
            opponent_id=opponent.id,
            battle_id=battle_id,
            protocol_id=protocol.id,
            axis=protocol.axis,
            hole=fighter.hole,
            answer=answer,
            better_answer=better,
            confidence=conf,
            role=role,
            failure_hint=hint,
        )
        rule = playbook.add_lesson(card)
        out.append(card.to_dict())
        bus.emit(
            "playbook.lesson",
            {"lesson": card.to_dict(), "rule_id": rule.id, "promoted": rule.promoted},
            actor="engine",
        )

    for rank, fid in enumerate(ranking):
        f = by_id[fid]
        ans = answers[fid]
        # Non-winners always get loser lessons
        if rank > 0 and winner_id:
            conf = 0.5 + 0.1 * rank
            add(f, by_id[winner_id], ans, winner_ans, conf, "loser")
            if f.hole == protocol.axis:
                add(
                    f,
                    by_id[winner_id],
                    ans,
                    winner_ans,
                    0.72,
                    "loser",
                    f"hole-axis miss on {protocol.axis}",
                )
        for h in _weakness_signals(ans, protocol, f):
            opp = by_id[winner_id] if winner_id and winner_id != fid else f
            add(f, opp, ans, winner_ans or ans, 0.5, "winner_weakness" if rank == 0 else "loser", h)

    if disagreement and disagreement.get("winner_mismatch"):
        # Doctrine from judge split
        detail = disagreement.get("detail", "judge disagreement")
        if winner_id:
            f = by_id[winner_id]
            add(
                f,
                f,
                answers.get(winner_id, ""),
                answers.get(winner_id, ""),
                0.55,
                "draw",
                f"dual-judge disagreement: {detail}",
            )
    return out


def _build_play_by_play(
    *,
    prompt: str,
    fighters: list[Fighter],
    answers: dict[str, str],
    judgment: dict[str, Any],
    lessons: list[dict[str, Any]],
    winner: str,
) -> list[dict[str, Any]]:
    timeline: list[dict[str, Any]] = []
    t = 0
    timeline.append({"t": t, "event": "prompt", "text": prompt[:2000]})
    t += 1
    for f in fighters:
        timeline.append(
            {
                "t": t,
                "event": "answer",
                "fighter": f.id,
                "mode": f.mode,
                "text": answers.get(f.id, "")[:2000],
            }
        )
        t += 1
    j1 = judgment["judge1"]
    j2 = judgment["judge2"]
    timeline.append(
        {
            "t": t,
            "event": "judge",
            "judge": 1,
            "ranking": j1["ranking"],
            "winner": j1.get("winner"),
            "note": j1["note"],
            "live": j1["live"],
        }
    )
    t += 1
    timeline.append(
        {
            "t": t,
            "event": "judge",
            "judge": 2,
            "ranking": j2["ranking"],
            "winner": j2.get("winner"),
            "note": j2["note"],
            "live": j2["live"],
        }
    )
    t += 1
    if judgment["disagreement"].get("winner_mismatch") or judgment["disagreement"].get(
        "full_order_mismatch"
    ):
        timeline.append(
            {
                "t": t,
                "event": "disagreement",
                "detail": judgment["disagreement"].get("detail", ""),
                "winner_mismatch": judgment["disagreement"].get("winner_mismatch"),
            }
        )
        t += 1
    timeline.append(
        {
            "t": t,
            "event": "ranking",
            "order": judgment["combined_ranking"],
            "rank_scores": judgment["rank_scores"],
            "winner": winner,
        }
    )
    t += 1
    if lessons:
        timeline.append(
            {
                "t": t,
                "event": "lessons",
                "count": len(lessons),
                "items": [
                    {"fighter_id": L.get("fighter_id"), "role": L.get("role"), "rule": (L.get("rule") or "")[:160]}
                    for L in lessons[:8]
                ],
            }
        )
    return timeline

__all__ = ['_emit_ffa_lessons', '_build_play_by_play']
