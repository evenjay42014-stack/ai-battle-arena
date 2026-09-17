"""Rebuild arena/data/snapshot.json from gzip b64 chunks."""
import base64, gzip
from pathlib import Path
root = Path(__file__).resolve().parent
b64 = (root / "_chunks/snap_gz_0.txt").read_text() + (root / "_chunks/snap_gz_1.txt").read_text()
out = root / "data" / "snapshot.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_bytes(gzip.decompress(base64.b64decode(b64)))
print("wrote", out, out.stat().st_size)
