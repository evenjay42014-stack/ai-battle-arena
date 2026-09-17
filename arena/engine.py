"""Fight engine: 4-fighter FFA, dual judges, play-by-play, curriculum.

Loaded from arena/_chunks_ffa/engine_*.txt so the source can ship as MCP-friendly chunks.
"""
from __future__ import annotations

from pathlib import Path as _Path

_chunk_dir = _Path(__file__).resolve().parent / "_chunks_ffa"
_parts = sorted(_chunk_dir.glob("engine_*.txt"))
if not _parts:
    raise ImportError("arena/_chunks_ffa/engine_*.txt missing — cannot load engine")
exec("".join(p.read_text(encoding="utf-8") for p in _parts), globals())
