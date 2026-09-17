"""One-shot rebuild of arena/review_council.py from uploaded chunks. Run: python3 -m arena._rebuild_review"""
import base64
from pathlib import Path
from arena._chunks.review_0 import CHUNK as C0
from arena._chunks.review_1 import CHUNK as C1
from arena._chunks.review_2 import CHUNK as C2
from arena._chunks.review_3 import CHUNK as C3
from arena._chunks.review_4 import CHUNK as C4
from arena._chunks.review_5 import CHUNK as C5
from arena._chunks.review_6 import CHUNK as C6
_path = Path(__file__).resolve().parent / "review_council.py"
_path.write_bytes(base64.b64decode(C0 + C1 + C2 + C3 + C4 + C5 + C6))
print("wrote", _path, "bytes", _path.stat().st_size)
