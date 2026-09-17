"""One-shot rebuild of arena/data/playbook.json from uploaded chunks. Run: python3 -m arena._rebuild_playbook"""
import base64
from pathlib import Path
from arena._chunks.playbook_0 import CHUNK as C0
from arena._chunks.playbook_1 import CHUNK as C1
from arena._chunks.playbook_2 import CHUNK as C2
from arena._chunks.playbook_3 import CHUNK as C3
from arena._chunks.playbook_4 import CHUNK as C4
_path = Path(__file__).resolve().parent / "data" / "playbook.json"
_path.write_bytes(base64.b64decode(C0 + C1 + C2 + C3 + C4))
print("wrote", _path, "bytes", _path.stat().st_size)
