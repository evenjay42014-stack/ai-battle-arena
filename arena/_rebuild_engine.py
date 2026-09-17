"""One-shot rebuild of arena/engine.py from uploaded chunks. Run: python3 -m arena._rebuild_engine"""
import base64
from pathlib import Path
from arena._chunks.engine_0 import CHUNK as C0
from arena._chunks.engine_1 import CHUNK as C1
from arena._chunks.engine_2 import CHUNK as C2
from arena._chunks.engine_3 import CHUNK as C3
from arena._chunks.engine_4 import CHUNK as C4
from arena._chunks.engine_5 import CHUNK as C5
_path = Path(__file__).resolve().parent / "engine.py"
_path.write_bytes(base64.b64decode(C0 + C1 + C2 + C3 + C4 + C5))
print("wrote", _path, "bytes", _path.stat().st_size)
