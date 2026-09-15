# NEXUS — AI Battle Arena

Every AI on one bus. They fight. Losses become doctrine.

NEXUS is a local multi-agent arena for stress-testing language models against each other across ten capability axes. After every match the loser receives a **lesson card**. Cards merge into a shared **playbook** that is injected into the next fight. Rankings use Elo + per-axis ratings.

This does **not** update model weights. Learning here is playbook distillation, strategy reuse, and weakness mining. That is honest.

## Quick start

```bash
python run_arena.py              # demo round-robin, print standings, write snapshot
python run_arena.py --serve      # command center at http://127.0.0.1:8765
```

Open `web/index.html` after `--serve`. FIGHT runs one protocol. TOURNAMENT runs a showcase round-robin.

## What is connected

Six evaluation personas sit on an append-only context bus:

| ID | Lab | Designed spike | Designed hole |
|---|---|---|---|
| `grok-4.6` | xAI | reasoning, metacognition | instruction (schema miss) |
| `claude-fable-5` | Anthropic | instruction, robustness | planning over-refusal |
| `gpt-6-astra` | OpenAI | coding, planning | knowledge (fake cites), metacognition |
| `gemini-3-ultra` | Google | memory, knowledge | robustness inverse-probes |
| `deepseek-v4` | DeepSeek | reasoning, coding | robustness |
| `llama-4-maverick` | Meta | instruction, playbook ingest | knowledge |

These are **eval personas with designed weaknesses**, not claims about shipping products. Swap them for real OpenAI-compatible endpoints later without changing protocols.

## Ten stress protocols

1. **Logic Gauntlet** — hidden premises, multi-hop, illegal-but-elegant answers
2. **Code Coliseum** — write it, then break the opponent; adversarial tests in the same turn
3. **Knowledge Crossfire** — facts, citations, abstention; invented DOIs lose
4. **Debate Pit** — Lincoln-Douglas peer battle + 3-judge committee, swapped order
5. **Constraint Forge** — novelty is worthless if a hard constraint breaks
6. **Instruction Siege** — system vs developer vs latest user
7. **Planning Raid** — tool timeouts, calendar conflicts; fabricated payloads lose
8. **Robustness Pit** — sycophancy, injection, paraphrase pairs; programmatic grader first
9. **Pressure Cooker** — several problems at once; drop a letter, drop the match
10. **Alignment Trial** — clean refusal vs over-refusal. Jailbreak compliance is never a win.

## How learning works

```
examiner question
  → independent answers
  → critique + follow-up
  → committee / programmatic score
  → Elo + axis ratings
  → lesson card
  → playbook.merge
  → next fight gets top-5 personal rules + 3 peer rules
```

Promote a rule when `count >= 2` and `mean(confidence) >= 0.6`. Drop it if a later ON vs OFF replay does not improve the targeted axis.

## Ratings

Classic Elo, K = 48 → 32 → 24 → 16 as games and RD settle. Draws shrink K. Capability-cup matches move the relevant axis faster. One match cannot swing more than ±64.

Radar axes: `reasoning knowledge coding planning instruction robustness creativity language memory metacognition`.

A high Elo with a hole in the radar is still a hole.

## Layout

```
run_arena.py              CLI + static server
arena/engine.py           pair, fight, ingest, snapshot
arena/rating.py           Elo / RD / axis ratings
arena/playbook.py         lesson cards
arena/protocols.py        10 modes + task pack
arena/bus.py              append-only event log
arena/agents.py           demo personas
arena/data/               fighters, battles, playbook, capabilities
web/index.html            command center
```

## Honest limits

- Demo fights use deterministic persona policies + strength draws, not live frontier APIs.
- Playbook injection is the learning channel. Fine-tunes / RL are out of scope for this repo.
- Seed transcripts are richer than live demo transcripts. Live mode still emits real Elo, lessons, and bus events.
- Do not treat persona leaderboard numbers as a public model ranking.

## Next

- Plug OpenAI-compatible `base_url` + `api_key` per fighter
- ON vs OFF playbook audits on replayed losses
- Bradley-Terry season rebuild with confidence intervals
- Human vote lane next to the committee
