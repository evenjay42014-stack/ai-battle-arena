"""Rebuild arena/data/playbook.json. Run: python3 -m arena._rebuild_playbook"""
import base64
from pathlib import Path
from arena._chunks.playbook_0 import CHUNK as C0
from arena._chunks.playbook_1 import CHUNK as C1
from arena._chunks.playbook_2 import CHUNK as C2
from arena._chunks.playbook_3 import CHUNK as C3
from arena._chunks.playbook_4 import CHUNK as C4
from arena._chunks.playbook_5 import CHUNK as C5
from arena._chunks.playbook_6 import CHUNK as C6
from arena._chunks.playbook_7 import CHUNK as C7
from arena._chunks.playbook_8 import CHUNK as C8
_path = Path(__file__).resolve().parent / "data" / "playbook.json"
_path.parent.mkdir(parents=True, exist_ok=True)
_path.write_bytes(base64.b64decode(C0 + C1 + C2 + C3 + C4 + C5 + C6 + C7 + C8))
print("wrote", _path, _path.stat().st_size)
