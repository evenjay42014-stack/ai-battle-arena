"""NEXUS AI Workstation — multi-provider collaborative app-building (not fighting)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from arena.agents import Fighter, build_roster
from arena.env_loader import load_dotenv, repo_root

ROLES: list[str] = [
    "architect",
    "implementer",
    "critic",
    "tester",
    "ux",
    "integrator",
]

ROLE_DEFS: dict[str, dict[str, str]] = {
    "architect": {
        "title": "Architect",
        "system": (
            "You are the Architect on a collaborative AI workstation. "
            "Design a clear system architecture for the product brief: components, "
            "data model, API boundaries, and key tradeoffs. Prefer concrete decisions "
            "over vague advice. Output: architecture overview, module list, risks."
        ),
        "user_prefix": "Produce an architecture plan for this brief.",
    },
    "implementer": {
        "title": "Implementer",
        "system": (
            "You are the Implementer. Write concrete starter code, file layout, and "
            "patch-style snippets that move the brief toward a working MVP. Prefer "
            "minimal deps, runnable structure, and clear next edits. Output: file tree "
            "+ key code snippets (not full novels)."
        ),
        "user_prefix": "Implement a practical MVP skeleton for this brief.",
    },
    "critic": {
        "title": "Critic",
        "system": (
            "You are the Critic. Challenge weak assumptions, missing constraints, "
            "security/privacy gaps, and over-engineering. Be specific and actionable. "
            "Output: ranked concerns, what to cut, what must not be skipped."
        ),
        "user_prefix": "Critique this product brief and typical MVP pitfalls.",
    },
    "tester": {
        "title": "Tester",
        "system": (
            "You are the Tester. Define acceptance criteria, edge cases, and a short "
            "test plan (manual + automated where cheap). Output: given/when/then cases "
            "and a smoke checklist for v0."
        ),
        "user_prefix": "Write a test plan and acceptance criteria for this brief.",
    },
    "ux": {
        "title": "UX",
        "system": (
            "You are the UX lead. Specify primary user flows, screen/wireframe notes, "
            "empty states, and accessibility basics for a desktop web MVP. Output: "
            "flow steps, UI inventory, copy tone notes."
        ),
        "user_prefix": "Design UX flows and UI inventory for this brief.",
    },
    "integrator": {
        "title": "Integrator",
        "system": (
            "You are the Integrator. Synthesize how pieces connect: env/config, "
            "build/run commands, integration seams, and a ship checklist. Output: "
            "runbook, integration map, next actions for the team."
        ),
        "user_prefix": "Produce an integration runbook and ship checklist for this brief.",
    },
}

DEFAULT_BRIEF = """# PulseBoard — collaborative status board MVP

Build a small multi-constraint web app: a team status board where each person posts a
short daily pulse (status + blocker + ETA), and the board aggregates them live.

## Must-haves
1. Local web UI (vanilla JS or minimal framework) + simple backend (Flask or FastAPI).
2. Persist pulses to SQLite; support create/edit/delete for the current user.
3. Columns or filters: Focus / Blocked / Done (or equivalent).
4. Server-sent updates or short polling so the board refreshes without a full reload.
5. Input validation + XSS-safe rendering of user text.
6. README with: setup, run, smoke test, and one sample seed command.

## Constraints
- Single machine / localhost first; no OAuth in v0.
- Keep dependencies minimal; stdlib + one web framework preferred.
- Clear file layout someone else can extend in one sitting.

## Stretch (optional, call out if deferred)
- Export JSON snapshot
- Dark/light theme toggle
- Simple webhook ping when someone marks Blocked

## Success
A new developer can clone, set up, run, post a pulse, see it on the board, and run a
smoke checklist in under 15 minutes.
"""


def _history_path() -> Path:
    return repo_root() / "arena" / "data" / "workstation_history.jsonl"


def _rotation_index() -> int:
    """Derive a fair rotation index from prior history length (and time)."""
    path = _history_path()
    n = 0
    if path.exists():
        try:
            n = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
        except OSError:
            n = 0
    return n


def assign_roles(
    roster: list[Fighter],
    rotation_index: int | None = None,
) -> dict[str, Fighter]:
    """Map ROLES → fighters with fair rotation so no provider is stuck in one role.

    rotation_index shifts which fighter gets which role. With 6 fighters and 6 roles,
    each full cycle of 6 runs gives every fighter every role once.
    """
    if not roster:
        raise ValueError("roster is empty")
    idx = _rotation_index() if rotation_index is None else int(rotation_index)
    n = len(roster)
    roles = list(ROLES)
    # If roster shorter than roles, cycle fighters; if longer, use first len(roles).
    mapping: dict[str, Fighter] = {}
    for i, role in enumerate(roles):
        fighter = roster[(i + idx) % n]
        mapping[role] = fighter
    return mapping


def default_brief(*, hard: bool = True) -> str:
    """Strong default product brief when the user leaves the textarea empty."""
    if not hard:
        return (
            "# Mini Notes — single-page notes app\n\n"
            "Local notes list with add/edit/delete, persisted to localStorage or SQLite. "
            "Minimal UI, no auth, README with run steps."
        )
    return DEFAULT_BRIEF.strip() + "\n"


def _build_user_prompt(
    role: str,
    brief: str,
    *,
    refine_context: dict[str, Any] | None = None,
) -> str:
    prefix = ROLE_DEFS[role]["user_prefix"]
    parts = [prefix, "", "## Product brief", brief.strip()]
    if refine_context:
        parts.append("")
        parts.append("## Prior workstation context (refine pass)")
        prior_plan = refine_context.get("plan") or ""
        if prior_plan:
            parts.append(f"Prior plan:\n{prior_plan}")
        prior_actions = refine_context.get("next_actions") or []
        if prior_actions:
            parts.append("Prior next actions:\n- " + "\n- ".join(str(a) for a in prior_actions[:8]))
        contribs = refine_context.get("contributions") or []
        if contribs:
            snippets = []
            for c in contribs[:6]:
                role_name = c.get("role", "?")
                text = (c.get("text") or "")[:400]
                snippets.append(f"[{role_name}] {text}")
            parts.append("Prior role outputs (trimmed):\n" + "\n---\n".join(snippets))
        parts.append("")
        parts.append(
            "Refine: improve specificity, resolve disagreements, and produce stronger "
            "patches / next actions than the prior pass."
        )
    return "\n".join(parts)


def _demo_enrich(fighter: Fighter, role: str, brief: str) -> str:
    """Richer DEMO replies so empty-key runs still look useful."""
    title = ROLE_DEFS[role]["title"]
    head = brief.strip().splitlines()[0].lstrip("# ").strip() if brief.strip() else "app"
    samples = {
        "architect": (
            f"{fighter.id} [{fighter.mode}] as {title}: propose modular layout for «{head}» — "
            f"UI / API / store layers; SQLite schema for pulses; SSE or 3s poll; "
            f"spike={fighter.spike}. Tradeoff: polling first, SSE as stretch."
        ),
        "implementer": (
            f"{fighter.id} [{fighter.mode}] as {title}: sketch `app.py`, `static/board.js`, "
            f"`schema.sql` with pulses(id, user, status, blocker, eta, ts). "
            f"Endpoints: GET/POST/PATCH/DELETE /api/pulses. Style={fighter.style}."
        ),
        "critic": (
            f"{fighter.id} [{fighter.mode}] as {title}: watch XSS on blocker text, missing "
            f"rate limits, and scope creep (webhooks). Cut theme toggle from v0. "
            f"hole={fighter.hole} — probe inverse cases early."
        ),
        "tester": (
            f"{fighter.id} [{fighter.mode}] as {title}: AC — create pulse → appears on board; "
            f"edit/delete; XSS payload shows escaped; offline DB survives restart. "
            f"Smoke: seed 3 users, mark one Blocked, confirm filter."
        ),
        "ux": (
            f"{fighter.id} [{fighter.mode}] as {title}: flow — open board → compose pulse → "
            f"see column update. Empty state copy: «No pulses yet — post the first.» "
            f"Keyboard: Enter to submit; aria-live on board region."
        ),
        "integrator": (
            f"{fighter.id} [{fighter.mode}] as {title}: runbook — `python3 -m venv .venv && "
            f"pip install -r requirements.txt && python app.py`. Next: wire schema, "
            f"board.js poll, README smoke section. Ship checklist: seed + XSS check."
        ),
    }
    return samples.get(role, fighter.answer(brief[:120], system=ROLE_DEFS[role]["system"]))


def _synthesize(
    contributions: list[dict[str, Any]],
    brief: str,
) -> tuple[str, list[str], list[str]]:
    """Build shared plan, disagreements, next_actions from role outputs (no extra API)."""
    by_role = {c["role"]: c for c in contributions}
    arch = (by_role.get("architect") or {}).get("text", "")
    impl = (by_role.get("implementer") or {}).get("text", "")
    integ = (by_role.get("integrator") or {}).get("text", "")

    plan_bits = [
        "Shared plan (synthesized from all six roles):",
        "1. Architect sets modules + data model.",
        "2. Implementer lands MVP skeleton + key snippets.",
        "3. UX defines primary flows and empty states.",
        "4. Tester locks acceptance criteria before polish.",
        "5. Critic cuts scope and flags security gaps.",
        "6. Integrator publishes runbook + ship checklist.",
    ]
    if arch:
        plan_bits.append(f"Architect signal: {arch[:220].rstrip()}…")
    if impl:
        plan_bits.append(f"Implementer signal: {impl[:220].rstrip()}…")
    plan = "\n".join(plan_bits)

    disagreements: list[str] = []
    critic_t = (by_role.get("critic") or {}).get("text", "")
    if critic_t and impl:
        disagreements.append(
            "Critic vs Implementer: watch scope — critic wants cuts; implementer may over-build. "
            "Prefer smallest runnable path first."
        )
    if (by_role.get("ux") or {}).get("text") and (by_role.get("tester") or {}).get("text"):
        disagreements.append(
            "UX vs Tester: polish vs coverage — ship flows that have acceptance tests; "
            "defer theme/animation."
        )
    if not disagreements:
        disagreements.append(
            "No hard conflict detected in DEMO synthesis — refine pass can surface sharper tradeoffs."
        )

    next_actions = [
        "Confirm v0 scope (must-haves only) from Critic cuts.",
        "Scaffold backend + SQLite schema from Architect/Implementer notes.",
        "Wire board UI + refresh from UX flow.",
        "Run Tester smoke checklist; fix XSS and persistence gaps.",
        "Publish Integrator README runbook; optionally Refine with this context.",
    ]
    if integ:
        next_actions.insert(0, f"Integrator cue: {integ[:160].rstrip()}…")

    # Brief title hint
    title_line = brief.strip().splitlines()[0] if brief.strip() else ""
    if title_line:
        next_actions.append(f"Keep working toward: {title_line.lstrip('#').strip()[:80]}")

    return plan, disagreements, next_actions


def _persist_history(record: dict[str, Any]) -> None:
    path = _history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    slim = {
        "ts": record.get("ts"),
        "brief_preview": (record.get("brief") or "")[:160],
        "roles": [c.get("role") for c in record.get("contributions") or []],
        "role_map": record.get("role_map"),
        "modes": {
            c.get("role"): c.get("mode") for c in (record.get("contributions") or [])
        },
        "refine": bool(record.get("refine_context_in")),
    }
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(slim, ensure_ascii=False) + "\n")
    except OSError:
        pass


def run_workstation(
    brief: str | None = None,
    *,
    refine_context: dict[str, Any] | None = None,
    prefer_live: bool = True,
    hard: bool = True,
    rotation_index: int | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Run all roster models on the same brief with rotated role assignment.

    Empty/None brief → strong default hard app-building brief (not an error).
    DEMO fighters work without API keys.
    """
    load_dotenv()
    text_brief = (brief or "").strip()
    used_default = not text_brief
    if used_default:
        text_brief = default_brief(hard=hard)

    roster = build_roster(prefer_live=prefer_live)
    role_map_fighters = assign_roles(roster, rotation_index=rotation_index)
    role_map = {
        role: {"fighter_id": f.id, "provider": f.provider, "lab": f.lab, "mode": f.mode}
        for role, f in role_map_fighters.items()
    }

    contributions: list[dict[str, Any]] = []
    for role, fighter in role_map_fighters.items():
        system = ROLE_DEFS[role]["system"]
        user = _build_user_prompt(role, text_brief, refine_context=refine_context)
        if fighter.mode == "DEMO":
            out = _demo_enrich(fighter, role, text_brief)
        else:
            try:
                out = fighter.answer(user, system=system)
            except Exception as e:  # noqa: BLE001
                out = f"[ERROR] {fighter.id}: {e}"
        contributions.append(
            {
                "role": role,
                "title": ROLE_DEFS[role]["title"],
                "provider": fighter.provider,
                "fighter_id": fighter.id,
                "lab": fighter.lab,
                "mode": fighter.mode,
                "text": out,
            }
        )

    plan, disagreements, next_actions = _synthesize(contributions, text_brief)

    # Context for a subsequent refine pass (slim)
    out_refine = {
        "brief": text_brief,
        "plan": plan,
        "next_actions": next_actions,
        "disagreements": disagreements,
        "contributions": [
            {"role": c["role"], "fighter_id": c["fighter_id"], "text": c["text"][:800]}
            for c in contributions
        ],
        "role_map": role_map,
    }

    result: dict[str, Any] = {
        "ok": True,
        "product": "NEXUS AI Workstation",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "brief": text_brief,
        "used_default_brief": used_default,
        "contributions": contributions,
        "plan": plan,
        "disagreements": disagreements,
        "next_actions": next_actions,
        "refine_context": out_refine,
        "role_map": role_map,
        "rotation_index": (
            _rotation_index() if rotation_index is None else int(rotation_index)
        ),
        "live_count": sum(1 for c in contributions if c["mode"] == "LIVE"),
        "demo_count": sum(1 for c in contributions if c["mode"] == "DEMO"),
    }

    if persist:
        _persist_history(
            {
                **result,
                "refine_context_in": refine_context is not None,
            }
        )
    return result


__all__ = [
    "ROLES",
    "ROLE_DEFS",
    "DEFAULT_BRIEF",
    "assign_roles",
    "default_brief",
    "run_workstation",
]
