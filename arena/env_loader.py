"""Load repo-root .env into os.environ (stdlib only)."""

from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_ENV = _REPO_ROOT / ".env"


def load_dotenv(path: str | Path | None = None, *, override: bool = False) -> Path | None:
    """Parse KEY=VALUE lines from .env into os.environ.

    Skips blank lines and comments. Does not print or return secret values.
    Returns the path loaded, or None if the file is missing.
    """
    env_path = Path(path) if path is not None else _DEFAULT_ENV
    if not env_path.is_file():
        return None

    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if override or key not in os.environ:
            os.environ[key] = value
    return env_path


def repo_root() -> Path:
    return _REPO_ROOT
