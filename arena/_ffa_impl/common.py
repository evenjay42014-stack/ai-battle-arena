"""Shared imports/constants for FFA engine parts."""
from __future__ import annotations

import json
import re
import time
from itertools import combinations
from pathlib import Path
from typing import Any, Sequence

from arena.agents import Fighter, build_roster, chat_completion_any
from arena.bus import ContextBus
from arena.playbook import Playbook, compact_lesson
from arena.protocols import PROTOCOLS, PROTOCOL_BY_ID, Protocol, protocol_at, protocols_for_hole

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
HISTORY_PATH = DATA_DIR / "battles_history.jsonl"
RANK_SCORES_4 = (1.0, 0.66, 0.33, 0.0)
