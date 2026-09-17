# NEXUS — AI Battle Arena

Every AI on one bus. They fight. Losses become doctrine.

NEXUS stress-tests language models against each other across ten capability axes. After every match the loser gets a **lesson card**. Cards merge into a shared **playbook** injected into the next fight. Project reviews weight each LIVE model by its strongest traits and feed disagreement lessons into the same playbook.

This does **not** update model weights. Learning is playbook distillation and weakness mining.

## Quick start

```bash
cp .env.example .env   # fill LIVE keys (never commit .env)
python3 run_arena.py --live-check
python3 run_arena.py --quick
python3 run_arena.py --tournament
python3 run_arena.py --review samples/sample_project_brief.md
python3 run_arena.py --reviews
python3 run_arena.py --serve --port 8899
```

Open `http://127.0.0.1:8899/view.html`. `.env` and directory listings are blocked.

## Env keys

`OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY` / `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `XAI_API_KEY`

## Learning loop

1. Ten stress protocols hit each fighter's designed holes.
2. Every battle emits dense lesson cards into `arena/data/playbook.json`.
3. The next fight injects the playbook immediately.
4. `--review` runs a multi-model council; disagreements become playbook lessons.

## CLI

| Flag | Purpose |
|---|---|
| `--live-check` | Probe providers |
| `--quick` | 3-pair smoke (persists playbook) |
| `--tournament` | Full learning stress suite |
| `--all-protocols` | Each pair × all 10 (expensive) |
| `--review TARGET` | Council review of a path, URL, or brief |
| `--review-max N` | Cap fighters for a review smoke |
| `--reviews` | List recent project reviews |
| `--serve` | Hardened static command center |

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
arena/data/          snapshot, playbook, reviews
samples/             example review brief
```
