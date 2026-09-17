"""Fight engine: 4-fighter FFA, dual judges, play-by-play, curriculum.

Implementation lives in arena._ffa_impl (split modules).
"""
from __future__ import annotations

from arena._ffa_impl import (  # noqa: F401
    DATA_DIR,
    HISTORY_PATH,
    RANK_SCORES_4,
    append_battle_history,
    build_learning_schedule,
    dual_judge,
    fight_four,
    fight_once,
    live_judge,
    live_judge_n,
    merge_battle_into_snapshot,
    round_robin,
    run_custom_battle,
    single_fight,
)

__all__ = [
    "DATA_DIR",
    "HISTORY_PATH",
    "RANK_SCORES_4",
    "append_battle_history",
    "build_learning_schedule",
    "dual_judge",
    "fight_four",
    "fight_once",
    "live_judge",
    "live_judge_n",
    "merge_battle_into_snapshot",
    "round_robin",
    "run_custom_battle",
    "single_fight",
]
