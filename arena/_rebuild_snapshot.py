"""One-shot rebuild of arena/data/snapshot.json from uploaded chunks. Run: python3 -m arena._rebuild_snapshot"""
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
_path = Path(__file__).resolve().parent / "data" / "snapshot.json"
_path.write_bytes(base64.b64decode(C0 + C1 + C2 + C3 + C4 + C5 + C6 + C7 + C8 + C9 + C10 + C11))
print("wrote", _path, "bytes", _path.stat().st_size)
