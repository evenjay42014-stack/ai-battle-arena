"""Rebuild arena/data/snapshot.json from gzip b64 chunks."""
import base64, gzip
from pathlib import Path
# force-run: 1
root = Path(__file__).resolve().parent
c0 = (root / "_chunks/snap_gz_0.txt").read_text().strip().replace("USEo", "UsEo", 1)
c1 = (root / "_chunks/snap_gz_1.txt").read_text().strip()
out = root / "data" / "snapshot.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_bytes(gzip.decompress(base64.b64decode(c0 + c1)))
print("wrote", out, out.stat().st_size)
