"""Rebuild arena/data/playbook.json from gzip b64 chunk."""
import base64, gzip
from pathlib import Path
root = Path(__file__).resolve().parent
b64 = (root / "_chunks/play_gz_0.txt").read_text().strip()
out = root / "data" / "playbook.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_bytes(gzip.decompress(base64.b64decode(b64)))
print("wrote", out, out.stat().st_size)
