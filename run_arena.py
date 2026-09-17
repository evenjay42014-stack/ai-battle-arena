#!/usr/bin/env python3
"""NEXUS AI Battle Arena CLI."""

from __future__ import annotations

import argparse
import http.server
import socketserver
import sys
from pathlib import Path

from arena.env_loader import load_dotenv, repo_root
from arena.live import run_live_checks


def cmd_live_check() -> int:
    results = run_live_checks()
    any_live = False
    for name, ok, detail in results:
        if ok:
            any_live = True
            print(f"[LIVE] {name}")
        else:
            print(f"[DEMO] {name} — {detail}")
    return 0 if any_live else 1


def cmd_fight() -> int:
    from arena.engine import round_robin

    # Keep default demo cheap: limit pairs so LIVE keys don't burn quota on full RR.
    # If any fighter is LIVE we still run a short showcase (3 pairs).
    snap = round_robin(limit_pairs=3)
    print("NEXUS standings")
    print("-" * 48)
    for row in snap["standings"]:
        print(
            f"{row['elo']:7.1f}  {row['wins']}-{row['losses']}  "
            f"[{row['mode']}] {row['id']} ({row['lab']})"
        )
    print("-" * 48)
    print(f"snapshot → arena/data/snapshot.json  battles={len(snap['battles'])}")
    return 0


def cmd_serve(port: int) -> int:
    root = repo_root()
    # Prefer web/ if present; else serve repo root (view.html).
    web = root / "web"
    directory = web if web.is_dir() else root

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)

    with socketserver.TCPServer(("127.0.0.1", port), Handler) as httpd:
        print(f"NEXUS command center http://127.0.0.1:{port}/")
        if (directory / "index.html").is_file():
            print(f"  open index.html under {directory}")
        elif (directory / "view.html").is_file():
            print(f"  open view.html under {directory}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    p = argparse.ArgumentParser(description="NEXUS — AI Battle Arena")
    p.add_argument(
        "--live-check",
        action="store_true",
        help="Probe each provider; exit 0 if any LIVE else 1",
    )
    p.add_argument(
        "--serve",
        action="store_true",
        help="Serve static UI (view.html / web/) on --port",
    )
    p.add_argument("--port", type=int, default=8765, help="HTTP port for --serve")
    args = p.parse_args(argv)

    if args.live_check:
        return cmd_live_check()
    if args.serve:
        return cmd_serve(args.port)
    return cmd_fight()


if __name__ == "__main__":
    sys.exit(main())
