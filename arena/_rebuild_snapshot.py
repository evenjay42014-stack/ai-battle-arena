"""Rebuild arena/data/snapshot.json. Run: python3 -m arena._rebuild_snapshot"""
import base64
from pathlib import Path
from arena._chunks.snapshot_0 import CHUNK as C0
from arena._chunks.snapshot_1 import CHUNK as C1
from arena._chunks.snapshot_2 import CHUNK as C2
from arena._chunks.snapshot_3 import CHUNK as C3
from arena._chunks.snapshot_4 import CHUNK as C4
from arena._chunks.snapshot_5 import CHUNK as C5
from arena._chunks.snapshot_6 import CHUNK as C6
from arena._chunks.snapshot_7 import CHUNK as C7
from arena._chunks.snapshot_8 import CHUNK as C8
from arena._chunks.snapshot_9 import CHUNK as C9
from arena._chunks.snapshot_10 import CHUNK as C10
from arena._chunks.snapshot_11 import CHUNK as C11
from arena._chunks.snapshot_12 import CHUNK as C12
from arena._chunks.snapshot_13 import CHUNK as C13
from arena._chunks.snapshot_14 import CHUNK as C14
from arena._chunks.snapshot_15 import CHUNK as C15
from arena._chunks.snapshot_16 import CHUNK as C16
from arena._chunks.snapshot_17 import CHUNK as C17
from arena._chunks.snapshot_18 import CHUNK as C18
from arena._chunks.snapshot_19 import CHUNK as C19
from arena._chunks.snapshot_20 import CHUNK as C20
from arena._chunks.snapshot_21 import CHUNK as C21
_path = Path(__file__).resolve().parent / "data" / "snapshot.json"
_path.parent.mkdir(parents=True, exist_ok=True)
_path.write_bytes(base64.b64decode(C0 + C1 + C2 + C3 + C4 + C5 + C6 + C7 + C8 + C9 + C10 + C11 + C12 + C13 + C14 + C15 + C16 + C17 + C18 + C19 + C20 + C21))
print("wrote", _path, _path.stat().st_size)
