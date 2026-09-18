#!/usr/bin/env python3
"""NEXUS AI Workstation CLI — collaborative multi-provider command center (+ legacy FFA)."""

from __future__ import annotations

import argparse
import json
import http.server
import socketserver
import sys
from pathlib import Path
from urllib.parse import urlparse

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


def cmd_tournament(
    *,
    limit_pairs: int | None = None,
    protocols_per_pair: int = 1,
    use_all_protocols: bool = False,
) -> int:
    from arena.agents import build_roster
    from arena.engine import round_robin
    from arena.protocols import PROTOCOLS

    roster = build_roster()
    live_n = sum(1 for f in roster if f.mode == "LIVE")
    print(f"NEXUS FFA tournament — {live_n}/{len(roster)} LIVE · 4-fighter · dual judges")
    print("Goal: dense lessons + hole curriculum + persisted playbook")
    print(f"Protocols ({len(PROTOCOLS)}): " + ", ".join(p.name for p in PROTOCOLS))
    print("-" * 60)
    snap = round_robin(
        roster,
        limit_pairs=limit_pairs,
        protocols_per_pair=protocols_per_pair,
        use_all_protocols=use_all_protocols,
        persist=True,
    )
    print("-" * 60)
    print("Standings (W = 1st place in FFA)")
    for row in snap["standings"]:
        d = row.get("elo_delta", 0)
        sign = "+" if d >= 0 else ""
        print(
            f"{row['elo']:7.1f} ({sign}{d})  {row['wins']}-{row['losses']}  "
            f"[{row['mode']}] {row['id']}  hole={row.get('hole','')}"
        )
    print("-" * 60)
    sig = snap.get("improvement_signals") or {}
    print(
        f"lessons_created={snap.get('lessons_created')}  "
        f"playbook_size={snap.get('playbook_size')}  "
        f"promoted={ (snap.get('playbook') or {}).get('promoted_count', 0) }  "
        f"avg_lessons/battle={sig.get('avg_lessons_per_battle')}  "
        f"hole_fights={sig.get('hole_protocol_fights')}  "
        f"judge_disagreements={sig.get('judge_disagreements')}"
    )
    print(
        f"protocols_used={len(snap.get('protocols_used') or [])}/10  "
        f"{snap.get('protocols_used')}  "
        f"judge_live={snap.get('judge_live_count')}  "
        f"fallback={snap.get('judge_fallback_count')}  "
        f"api_failures={snap.get('api_failures', 0)}"
    )
    print("snapshot → arena/data/snapshot.json  playbook → arena/data/playbook.json")
    return 0


def cmd_fight_quick() -> int:
    from arena.engine import round_robin

    snap = round_robin(limit_pairs=2, protocols_per_pair=1, persist=True)
    print("NEXUS quick (2 FFA groups, still learns)")
    for row in snap["standings"]:
        print(
            f"{row['elo']:7.1f}  {row['wins']}-{row['losses']}  "
            f"[{row['mode']}] {row['id']}"
        )
    print(
        f"lessons_created={snap.get('lessons_created')}  "
        f"playbook_size={snap.get('playbook_size')}  battles={len(snap['battles'])}"
    )
    return 0


def cmd_review(target: str, *, max_fighters: int | None = None) -> int:
    from arena.review_council import submit_review

    print(f"NEXUS review council ← {target!r}")
    rec = submit_review(target, max_fighters=max_fighters)
    print(f"id={rec['id']}  type={rec['project_type']}  decision={rec['decision'].upper()}")
    shares = rec.get("shares") or {}
    print(
        "shares  "
        + "  ".join(f"{k}={shares.get(k, 0):.0%}" for k in ("approve", "revise", "reject"))
    )
    for r in rec.get("reviews") or []:
        print(
            f"  [{r['mode']}] {r['fighter_id']:20s}  vote={r['vote']:7s}  "
            f"w={r['weight']:.2f}  conf={float(r['confidence']):.2f}  "
            f"spike={r['spike']}/{r['hole']}"
        )
        if r.get("summary"):
            print(f"         {str(r['summary'])[:140]}")
    if rec.get("disagreements"):
        print(f"disagreement lessons → {rec.get('lessons_path')}")
    print(f"saved → {rec.get('path')}  feed → arena/data/review_feed.jsonl")
    return 0


def cmd_reviews(limit: int = 15) -> int:
    from arena.review_council import list_reviews

    rows = list_reviews(limit=limit)
    if not rows:
        print("No reviews yet. Submit with: python3 run_arena.py --review TARGET")
        return 0
    print(f"Recent reviews ({len(rows)})")
    for r in rows:
        print(
            f"  {r.get('ts', '')}  {str(r.get('decision', '?')):7s}  "
            f"type={r.get('project_type', '')}  {str(r.get('title', ''))[:50]}  "
            f"id={r.get('id', '')}"
        )
    return 0


def cmd_serve(port: int) -> int:
    root = repo_root()
    blocked = {".env", ".git"}
    data_dir = root / "arena" / "data"

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def translate_path(self, path: str) -> str:
            mapped = super().translate_path(path)
            rp = Path(mapped).resolve()
            try:
                rp.relative_to(root)
            except ValueError:
                return str(root / "view.html")
            if rp.name == ".env" or any(part in blocked for part in rp.parts):
                return str(root / "view.html")
            return mapped

        def list_directory(self, path: str):
            self.path = "/view.html"
            return self.send_head()

        def _send_json(self, code: int, payload: dict | list) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _read_json_body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError as e:
                raise ValueError(f"invalid JSON: {e}") from e
            if not isinstance(data, dict):
                raise ValueError("JSON body must be an object")
            return data

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path
            if path in ("/", ""):
                self.path = "/view.html"
                return super().do_GET()
            if path == "/api/snapshot":
                snap_path = data_dir / "snapshot.json"
                if not snap_path.exists():
                    return self._send_json(404, {"error": "no snapshot yet"})
                try:
                    data = json.loads(snap_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    return self._send_json(500, {"error": "corrupt snapshot"})
                return self._send_json(200, data)
            if path == "/api/history":
                hist = data_dir / "battles_history.jsonl"
                rows: list[dict] = []
                if hist.exists():
                    for line in hist.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rows.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
                # Also fall back to snapshot battles
                if not rows:
                    snap_path = data_dir / "snapshot.json"
                    if snap_path.exists():
                        try:
                            snap = json.loads(snap_path.read_text(encoding="utf-8"))
                            rows = list(snap.get("battles") or [])
                        except json.JSONDecodeError:
                            pass
                return self._send_json(200, {"battles": rows[-50:], "count": len(rows)})
            if path == "/api/workstation":
                return self._send_json(
                    405,
                    {"error": "Use POST /api/workstation with JSON {brief?, refine_context?, hard?}"},
                )
            if path == "/api/battle":
                return self._send_json(
                    405,
                    {"error": "Use POST /api/battle with JSON {prompt?, protocol_id?} — empty prompt uses hardest protocol"},
                )
            return super().do_GET()

        def do_POST(self):
            parsed = urlparse(self.path)
            path = parsed.path

            if path == "/api/workstation":
                try:
                    body = self._read_json_body()
                except ValueError as e:
                    return self._send_json(400, {"error": str(e)})
                brief = body.get("brief")
                if brief is not None and not isinstance(brief, str):
                    return self._send_json(400, {"error": "brief must be a string"})
                refine_context = body.get("refine_context")
                if refine_context is not None and not isinstance(refine_context, dict):
                    return self._send_json(400, {"error": "refine_context must be an object"})
                hard = body.get("hard", True)
                try:
                    from arena.workstation import run_workstation

                    out = run_workstation(
                        brief,
                        refine_context=refine_context,
                        hard=bool(hard),
                        prefer_live=True,
                    )
                except Exception as e:  # noqa: BLE001
                    return self._send_json(500, {"error": str(e)})
                return self._send_json(200, out)

            if path != "/api/battle":
                self.send_error(404, "Not Found")
                return
            try:
                body = self._read_json_body()
            except ValueError as e:
                return self._send_json(400, {"error": str(e)})

            # Prompt is optional: empty → hardest protocol generator on the server
            prompt = (body.get("prompt") or "").strip()
            protocol_id = body.get("protocol_id") or None
            fighter_ids = body.get("fighter_ids") or None
            hard = body.get("hard", True)

            try:
                from arena.engine import run_custom_battle

                out = run_custom_battle(
                    prompt or None,
                    protocol_id=protocol_id,
                    fighter_ids=fighter_ids,
                    hard=bool(hard),
                )
            except Exception as e:  # noqa: BLE001
                return self._send_json(500, {"error": str(e)})

            battle = out["battle"]
            return self._send_json(
                200,
                {
                    "ok": True,
                    "battle": battle,
                    "winner": battle.get("winner"),
                    "ranking": battle.get("ranking"),
                    "play_by_play": battle.get("play_by_play"),
                    "disagreement": battle.get("disagreement"),
                    "standings": (out.get("snapshot") or {}).get("standings"),
                },
            )

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", port), Handler) as httpd:
        print(f"NEXUS AI Workstation http://127.0.0.1:{port}/view.html")
        print("  API: POST /api/workstation  POST /api/battle (legacy)")
        print("       GET /api/snapshot  GET /api/history")
        print("  .env and directory listing are blocked")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    p = argparse.ArgumentParser(
        description="NEXUS — AI Workstation (collaborate) + legacy FFA arena"
    )
    p.add_argument("--live-check", action="store_true", help="Probe providers")
    p.add_argument("--serve", action="store_true", help="Workstation UI + /api/workstation (+ legacy /api/battle)")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--review", metavar="TARGET", help="Council review: path, URL, or brief text/file")
    p.add_argument("--reviews", action="store_true", help="List recent project reviews")
    p.add_argument("--review-max", type=int, default=None, help="Cap fighters for a review (smoke)")
    p.add_argument("--tournament", action="store_true", help="Full learning stress suite (default)")
    p.add_argument("--quick", action="store_true", help="2-group FFA smoke (still persists playbook)")
    p.add_argument("--all-protocols", action="store_true", help="Each group × all 10 (expensive)")
    p.add_argument("--protocols-per-pair", type=int, default=1)
    p.add_argument("--limit-pairs", type=int, default=None, help="Limit FFA groups (alias)")
    args = p.parse_args(argv)

    if args.live_check:
        return cmd_live_check()
    if args.reviews:
        return cmd_reviews()
    if args.review:
        return cmd_review(args.review, max_fighters=args.review_max)
    if args.serve:
        return cmd_serve(args.port)
    if args.quick:
        return cmd_fight_quick()
    return cmd_tournament(
        limit_pairs=args.limit_pairs,
        protocols_per_pair=args.protocols_per_pair,
        use_all_protocols=args.all_protocols,
    )


if __name__ == "__main__":
    sys.exit(main())
