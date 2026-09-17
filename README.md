# NEXUS — AI Battle Arena

Every AI on one bus. They fight. Losses become doctrine.

NEXUS stress-tests language models in **4-fighter free-for-alls** across ten hard protocols. Each battle is scored by **two independent judges**. After every match losers (and weakness signals) get **lesson cards** that merge into a shared **playbook** injected into the next fight. The command center shows sports-style **play-by-play**.

This does **not** update model weights. Learning is playbook distillation and weakness mining.

## Quick start

```bash
cp .env.example .env   # fill LIVE keys (never commit .env)
python3 run_arena.py --live-check
python3 run_arena.py --quick          # 2 FFA groups (DEMO or LIVE)
python3 run_arena.py --tournament     # full hard curriculum
python3 run_arena.py --review samples/sample_project_brief.md
python3 run_arena.py --serve --port 8899
```

Open `http://127.0.0.1:8899/view.html`. Use the **prompt bar** to launch a custom 4-way fight (POST `/api/battle`). `.env` and directory listings are blocked.

On static GitHub Pages there is no API — the UI shows how to enable live fights with `--serve`, and still renders play-by-play from `arena/data/snapshot.json`.

## Command center API (`--serve`)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/battle` | JSON `{ "prompt": "...", "protocol_id?": "...", "hard?": true }` → run FFA, return ranking + play-by-play |
| `GET` | `/api/snapshot` | Current standings / battles / playbook snapshot |
| `GET` | `/api/history` | Recent battles (from `battles_history.jsonl` or snapshot) |

## What's new (Command Center FFA)

1. **Prompt bar** — custom challenges with a real fight loop (not a fake UI).
2. **Hard protocols** — adversarial, multi-constraint tasks; `hard=True` by default.
3. **4-fighter FFA** — ranked rounds; Elo from rank scores `1.0 / 0.66 / 0.33 / 0.0`; W-L counts 1st place as a win.
4. **Dual judges** — two independent LIVE judges (heuristic fallback); disagreements surface in play-by-play and can emit lessons.
5. **Play-by-play** — timeline: prompt → each answer → judge1/judge2 → ranking → lessons.

## Env keys

`OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY` / `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `XAI_API_KEY`

## Learning loop

1. Ten hard protocols hit each fighter's designed holes.
2. Every battle emits dense lesson cards into `arena/data/playbook.json`.
3. The next fight injects the playbook immediately.
4. `--review` runs a multi-model council; disagreements become playbook lessons.

## CLI

| Flag | Purpose |
|---|---|
| `--live-check` | Probe providers |
| `--quick` | 2-group FFA smoke (persists playbook) |
| `--tournament` | Full learning stress suite |
| `--all-protocols` | Each group × all 10 (expensive) |
| `--review TARGET` | Council review of a path, URL, or brief |
| `--review-max N` | Cap fighters for a review smoke |
| `--reviews` | List recent project reviews |
| `--serve` | Command center + battle API |

## Layout

```
run_arena.py
view.html
arena/agents.py
arena/engine.py
arena/protocols.py
arena/playbook.py
arena/review_council.py
arena/live.py
arena/data/          snapshot, playbook, battles_history, reviews
samples/             example review brief
```
