# NEXUS AI Workstation

Command center where **all six live AI providers collaborate** to build and refine apps — not fight.

Roles rotate fairly across runs: **architect · implementer · critic · tester · ux · integrator**. Shared output includes a plan, patches/snippets, disagreements, and next actions. Empty brief → a strong default hard app-building task.

The legacy 4-fighter FFA / dual-judge / playbook engine is still in the repo (`--tournament`, `POST /api/battle`) but is not the main product flow.

## Quick start

```bash
cp .env.example .env   # fill LIVE keys (never commit .env)
python3 run_arena.py --live-check
python3 run_arena.py --serve --port 8899
```

Open `http://127.0.0.1:8899/view.html`. Use **Run workstation** (POST `/api/workstation`). Leave the brief blank for the default PulseBoard MVP. Use **Refine** to run again with prior context. Attach images and text/code/pdf/zip via the file picker (JSON base64; ≤8 MB decoded total).

On static GitHub Pages there is no API — the UI explains how to enable live runs with `--serve`.

## Command center API (`--serve`)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/workstation` | JSON `{ "brief?", "refine_context?", "hard?", "attachments?" }` → role contributions + plan. Attachments: `[{name, mime, data_b64}]` (≤8 MB decoded). Text inlined into brief; images sent to vision-capable providers (openai/anthropic/google/xai/openrouter); deepseek gets text stub only. |
| `POST` | `/api/battle` | Legacy FFA (optional) |
| `GET` | `/api/snapshot` | Legacy standings / battles snapshot |
| `GET` | `/api/history` | Recent legacy battles |

## Env keys

`OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY` / `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `XAI_API_KEY`

## CLI

| Flag | Purpose |
|---|---|
| `--live-check` | Probe providers |
| `--serve` | Workstation UI + `/api/workstation` (+ legacy `/api/battle`) |
| `--quick` | Legacy 2-group FFA smoke |
| `--tournament` | Legacy full learning stress suite |
| `--review TARGET` | Legacy council review |

## Layout

```
run_arena.py
view.html          # workstation UI entry
index.html         # redirect → view.html
arena/workstation.py
arena/agents.py    # LIVE wiring (xai/openai/anthropic/google/deepseek/openrouter)
arena/engine.py    # legacy FFA (kept)
arena/data/        # snapshot, playbook, workstation_history.jsonl
samples/
```
