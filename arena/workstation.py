"""NEXUS AI Workstation — multi-provider collaborative app-building (not fighting)."""

from __future__ import annotations

import base64
import binascii
import io
import json
import time
import zipfile
from pathlib import Path
from typing import Any

from arena.agents import DEMO_PERSONAS, Fighter, build_roster
from arena.env_loader import load_dotenv, repo_root

# Total decoded attachment payload cap (sum of raw bytes after base64 decode).
MAX_ATTACHMENTS_DECODED = 8 * 1024 * 1024
MAX_TEXT_CHARS_PER_FILE = 40_000
MAX_ZIP_MEMBER_CHARS = 12_000
MAX_ZIP_TEXT_MEMBERS = 8

_TEXT_EXTS = {
    ".txt", ".md", ".markdown", ".json", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".html", ".htm", ".css", ".csv", ".yml", ".yaml", ".toml", ".xml", ".svg",
    ".sh", ".rs", ".go", ".java", ".c", ".h", ".cpp", ".rb", ".php",
}
_TEXT_MIMES = {
    "text/plain", "text/markdown", "text/csv", "text/html", "text/css",
    "text/javascript", "application/javascript", "application/json",
    "application/xml", "text/xml", "application/x-python", "text/x-python",
}
_IMAGE_MIMES = {
    "image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif",
}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_PDF_MIMES = {"application/pdf"}
_ZIP_MIMES = {"application/zip", "application/x-zip-compressed"}

# Providers where chat helpers can receive image parts (see arena/agents.py).
VISION_PROVIDERS = frozenset({"openai", "anthropic", "google", "xai", "openrouter"})


class AttachmentError(ValueError):
    """Client-facing attachment validation / size error (map to HTTP 400)."""


def _safe_name(name: str) -> str:
    base = Path(str(name or "file").replace("\\", "/")).name.strip() or "file"
    return base[:180]


def _ext(name: str) -> str:
    return Path(name).suffix.lower()


def _is_image(name: str, mime: str) -> bool:
    m = (mime or "").lower().split(";")[0].strip()
    if m in _IMAGE_MIMES or m == "image/jpg":
        return True
    return _ext(name) in _IMAGE_EXTS


def _is_pdf(name: str, mime: str) -> bool:
    m = (mime or "").lower().split(";")[0].strip()
    return m in _PDF_MIMES or _ext(name) == ".pdf"


def _is_zip(name: str, mime: str) -> bool:
    m = (mime or "").lower().split(";")[0].strip()
    return m in _ZIP_MIMES or _ext(name) == ".zip"


def _is_text_like(name: str, mime: str) -> bool:
    m = (mime or "").lower().split(";")[0].strip()
    if m.startswith("text/") or m in _TEXT_MIMES:
        return True
    return _ext(name) in _TEXT_EXTS


def _decode_text(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="replace")


def _truncate(text: str, limit: int = MAX_TEXT_CHARS_PER_FILE) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit] + f"\n…[truncated at {limit} chars]", True


def _pdf_note(name: str, raw: bytes) -> str:
    """Best-effort PDF note without heavy deps; try crude stream text extract."""
    note = f"[attached PDF: {name} ({len(raw)} bytes)"
    # Crude extract: printable runs from uncompressed streams (often empty for modern PDFs).
    try:
        # Look for simple text between parentheses in content streams (very limited).
        sample = raw[:200_000]
        chunks: list[str] = []
        i = 0
        while i < len(sample) and len(chunks) < 40:
            if sample[i : i + 1] == b"(":
                j = i + 1
                buf = bytearray()
                while j < len(sample) and sample[j : j + 1] != b")":
                    if sample[j : j + 1] == b"\\" and j + 1 < len(sample):
                        buf.append(sample[j + 1])
                        j += 2
                        continue
                    buf.append(sample[j])
                    j += 1
                    if len(buf) > 200:
                        break
                if 3 <= len(buf) <= 200:
                    try:
                        t = buf.decode("latin-1", errors="ignore").strip()
                    except Exception:
                        t = ""
                    if t and t.isprintable():
                        chunks.append(t)
                i = j + 1
            else:
                i += 1
        if chunks:
            joined = " ".join(chunks)[:1500]
            return note + f"; crude text extract]\n{joined}"
    except Exception:
        pass
    return note + "; binary/PDF text extraction limited without extra deps — use vision/notes]"


def _zip_sections(name: str, raw: bytes) -> list[str]:
    sections: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = zf.namelist()
            listing = ", ".join(names[:30])
            if len(names) > 30:
                listing += f", …(+{len(names) - 30} more)"
            sections.append(f"### Attachment: {name} (zip, {len(raw)} bytes)\nMembers: {listing}")
            taken = 0
            for info in zf.infolist():
                if taken >= MAX_ZIP_TEXT_MEMBERS:
                    break
                if info.is_dir() or info.file_size > 200_000:
                    continue
                inner = info.filename
                if not _is_text_like(inner, ""):
                    continue
                try:
                    data = zf.read(info)
                except Exception:
                    continue
                text, _ = _truncate(_decode_text(data), MAX_ZIP_MEMBER_CHARS)
                sections.append(f"### Zip member: {name} → {inner}\n```\n{text}\n```")
                taken += 1
    except zipfile.BadZipFile:
        sections.append(f"### Attachment: {name}\n[invalid zip]")
    return sections


def process_attachments(
    attachments: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Validate + decode attachments. Returns brief_extra, images, meta.

    images: [{name, mime, data_b64, nbytes}] for vision-capable providers.
    Raises AttachmentError on invalid input or oversize.
    """
    if attachments is None:
        return {"brief_extra": "", "images": [], "meta": []}
    if not isinstance(attachments, list):
        raise AttachmentError("attachments must be a list of {name, mime, data_b64}")

    total = 0
    sections: list[str] = []
    images: list[dict[str, Any]] = []
    meta: list[dict[str, Any]] = []

    for i, item in enumerate(attachments):
        if not isinstance(item, dict):
            raise AttachmentError(f"attachments[{i}] must be an object")
        name = _safe_name(item.get("name") or f"file_{i}")
        mime = str(item.get("mime") or "application/octet-stream").strip()
        b64 = item.get("data_b64")
        if not isinstance(b64, str) or not b64.strip():
            raise AttachmentError(f"attachments[{i}] ({name}): data_b64 required")
        # Allow data-URL prefix
        if "," in b64 and b64.strip().lower().startswith("data:"):
            b64 = b64.split(",", 1)[1]
        try:
            raw = base64.b64decode(b64, validate=False)
        except (binascii.Error, ValueError) as e:
            raise AttachmentError(f"attachments[{i}] ({name}): invalid base64 ({e})") from e
        total += len(raw)
        if total > MAX_ATTACHMENTS_DECODED:
            raise AttachmentError(
                f"attachments exceed {MAX_ATTACHMENTS_DECODED // (1024 * 1024)} MB "
                f"decoded limit (got ~{total} bytes). Remove files or shrink payload."
            )

        entry = {"name": name, "mime": mime, "nbytes": len(raw)}
        meta.append(entry)

        if _is_image(name, mime):
            images.append({
                "name": name,
                "mime": "image/jpeg" if mime.lower() in ("image/jpg",) else (
                    mime.lower().split(";")[0].strip() or "image/png"
                ),
                "data_b64": base64.b64encode(raw).decode("ascii"),
                "nbytes": len(raw),
            })
            sections.append(
                f"### Attachment: {name}\n"
                f"[attached image: {name} ({mime}, {len(raw)} bytes)]"
            )
        elif _is_pdf(name, mime):
            sections.append(f"### Attachment: {name}\n{_pdf_note(name, raw)}")
        elif _is_zip(name, mime):
            sections.extend(_zip_sections(name, raw))
        elif _is_text_like(name, mime):
            text, trunc = _truncate(_decode_text(raw))
            fence = "```"
            sections.append(
                f"### Attachment: {name} ({mime}, {len(raw)} bytes"
                + (", truncated" if trunc else "")
                + f")\n{fence}\n{text}\n{fence}"
            )
        else:
            sections.append(
                f"### Attachment: {name}\n"
                f"[attached binary: {name} ({mime}, {len(raw)} bytes) — not inlined]"
            )

    brief_extra = ""
    if sections:
        brief_extra = (
            "\n\n## Uploaded attachments\n\n" + "\n\n".join(sections) + "\n"
        )
    return {"brief_extra": brief_extra, "images": images, "meta": meta}

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


def ensure_full_roster(roster: list[Fighter] | None = None, *, prefer_live: bool = True) -> list[Fighter]:
    """Guarantee exactly one fighter per lab/provider (len == 6).

    Pads from DEMO_PERSONAS if build_roster ever returns fewer; never skips a
    provider that belongs on the workstation. Role rotation remaps roles only —
    every roster member still contributes.
    """
    base = list(roster) if roster is not None else build_roster(prefer_live=prefer_live)
    by_provider: dict[str, Fighter] = {}
    for f in base:
        # Keep first sighting of each provider (stable order from DEMO_PERSONAS).
        if f.provider not in by_provider:
            by_provider[f.provider] = f

    out: list[Fighter] = []
    for persona in DEMO_PERSONAS:
        prov = persona["provider"]
        if prov in by_provider:
            out.append(by_provider.pop(prov))
            continue
        # Pad missing provider as DEMO so Run still attempts 6 contributions.
        out.append(
            Fighter(
                id=persona["id"],
                lab=persona["lab"],
                provider=persona["provider"],
                spike=persona["spike"],
                hole=persona["hole"],
                style=persona["style"],
                mode="DEMO",
            )
        )
    if len(out) != 6:
        raise RuntimeError(f"ensure_full_roster expected 6 fighters, got {len(out)}")
    return out


def assign_roles(
    roster: list[Fighter],
    rotation_index: int | None = None,
) -> dict[str, Fighter]:
    """Map ROLES → fighters with fair rotation so no provider is stuck in one role.

    Always includes every roster member when len(roster)==6 (one role each).
    rotation_index shifts which fighter gets which role; a full cycle of 6 runs
    gives every fighter every role once. Never skips a fighter to shrink the map.
    """
    roster = ensure_full_roster(roster)
    idx = _rotation_index() if rotation_index is None else int(rotation_index)
    n = len(roster)
    roles = list(ROLES)
    mapping: dict[str, Fighter] = {}
    for i, role in enumerate(roles):
        fighter = roster[(i + idx) % n]
        mapping[role] = fighter
    # Invariant: 6 roles, 6 distinct fighters (one per provider/lab).
    ids = [f.id for f in mapping.values()]
    if len(mapping) != 6 or len(set(ids)) != 6:
        raise RuntimeError(
            f"assign_roles must map 6 distinct fighters, got {len(mapping)} roles / "
            f"{len(set(ids))} ids: {ids}"
        )
    return mapping


def _extract_error(text: str) -> str | None:
    """Surface LIVE failures as a dedicated field for the UI."""
    t = (text or "").strip()
    for prefix in ("[LIVE ERROR]", "[ERROR]"):
        if t.startswith(prefix):
            return t[len(prefix):].strip() or t
    return None


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
) -> tuple[str, list[str], list[str], list[str]]:
    """Build shared plan, patches, disagreements, next_actions from all six role outputs."""
    by_role = {c["role"]: c for c in contributions}
    arch = (by_role.get("architect") or {}).get("text", "")
    impl = (by_role.get("implementer") or {}).get("text", "")
    integ = (by_role.get("integrator") or {}).get("text", "")
    ux_t = (by_role.get("ux") or {}).get("text", "")
    test_t = (by_role.get("tester") or {}).get("text", "")
    critic_t = (by_role.get("critic") or {}).get("text", "")

    plan_bits = [
        "Shared plan (synthesized from all six providers/roles):",
        "1. Architect sets modules + data model.",
        "2. Implementer lands MVP skeleton + key snippets.",
        "3. UX defines primary flows and empty states.",
        "4. Tester locks acceptance criteria before polish.",
        "5. Critic cuts scope and flags security gaps.",
        "6. Integrator publishes runbook + ship checklist.",
    ]
    for role_key, label, blob in (
        ("architect", "Architect", arch),
        ("implementer", "Implementer", impl),
        ("ux", "UX", ux_t),
        ("tester", "Tester", test_t),
        ("critic", "Critic", critic_t),
        ("integrator", "Integrator", integ),
    ):
        if blob:
            plan_bits.append(f"{label} signal: {blob[:200].rstrip()}…")
    plan = "\n".join(plan_bits)

    patches: list[str] = []
    if impl:
        patches.append(f"Implementer patch cues: {impl[:280].rstrip()}…")
    if arch:
        patches.append(f"Architecture seam to land first: {arch[:200].rstrip()}…")
    if integ:
        patches.append(f"Integration / runbook patch: {integ[:200].rstrip()}…")
    if ux_t:
        patches.append(f"UX copy/flow patch: {ux_t[:180].rstrip()}…")
    if not patches:
        patches.append(
            "No concrete patches yet — Refine with prior outputs so all six improve specificity."
        )

    disagreements: list[str] = []
    if critic_t and impl:
        disagreements.append(
            "Critic vs Implementer: watch scope — critic wants cuts; implementer may over-build. "
            "Prefer smallest runnable path first."
        )
    if ux_t and test_t:
        disagreements.append(
            "UX vs Tester: polish vs coverage — ship flows that have acceptance tests; "
            "defer theme/animation."
        )
    if arch and critic_t:
        disagreements.append(
            "Architect vs Critic: validate must-haves against critic cuts before locking modules."
        )
    live_errs = [c for c in contributions if c.get("error")]
    if live_errs:
        names = ", ".join(f"{c.get('fighter_id')} ({c.get('role')})" for c in live_errs[:4])
        disagreements.append(
            f"Provider gaps: {names} returned LIVE errors — treat those role outputs as incomplete."
        )
    if not disagreements:
        disagreements.append(
            "No hard conflict detected — refine pass can surface sharper tradeoffs across all six."
        )

    next_actions = [
        "Confirm v0 scope (must-haves only) from Critic cuts.",
        "Scaffold backend + schema from Architect/Implementer notes.",
        "Wire primary UI flow from UX; attach Tester acceptance checks.",
        "Fix any LIVE errors, then Refine so all six improve the same ask.",
        "Publish Integrator README runbook + smoke checklist.",
    ]
    if integ:
        next_actions.insert(0, f"Integrator cue: {integ[:160].rstrip()}…")

    title_line = brief.strip().splitlines()[0] if brief.strip() else ""
    if title_line:
        next_actions.append(f"Keep working toward: {title_line.lstrip('#').strip()[:80]}")

    return plan, patches, disagreements, next_actions


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
    attachments: list[dict[str, Any]] | None = None,
    prefer_live: bool = True,
    hard: bool = True,
    rotation_index: int | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Run all roster models on the same brief with rotated role assignment.

    Empty/None brief → strong default hard app-building brief (not an error).
    DEMO fighters work without API keys.

    attachments: optional [{name, mime, data_b64}] — text inlined into brief;
    images passed to vision-capable providers when LIVE.
    """
    load_dotenv()
    processed = process_attachments(attachments)
    text_brief = (brief or "").strip()
    used_default = not text_brief
    if used_default:
        text_brief = default_brief(hard=hard)
    if processed["brief_extra"]:
        text_brief = text_brief.rstrip() + processed["brief_extra"]

    images = processed["images"]
    roster = ensure_full_roster(build_roster(prefer_live=prefer_live), prefer_live=prefer_live)
    role_map_fighters = assign_roles(roster, rotation_index=rotation_index)
    role_map = {
        role: {"fighter_id": f.id, "provider": f.provider, "lab": f.lab, "mode": f.mode}
        for role, f in role_map_fighters.items()
    }

    contributions: list[dict[str, Any]] = []
    for role, fighter in role_map_fighters.items():
        system = ROLE_DEFS[role]["system"]
        user = _build_user_prompt(role, text_brief, refine_context=refine_context)
        vision = images if fighter.provider in VISION_PROVIDERS else None
        err: str | None = None
        if fighter.mode == "DEMO":
            out = _demo_enrich(fighter, role, text_brief)
            if images:
                out += f"\n[attachments: {len(images)} image(s) noted in brief; DEMO has no vision]"
        else:
            try:
                out = fighter.answer(user, system=system, images=vision)
            except Exception as e:  # noqa: BLE001
                out = f"[ERROR] {fighter.id}: {e}"
                err = str(e)
            if err is None:
                err = _extract_error(out)
        contributions.append(
            {
                "role": role,
                "title": ROLE_DEFS[role]["title"],
                "provider": fighter.provider,
                "fighter_id": fighter.id,
                "lab": fighter.lab,
                "mode": fighter.mode,
                "text": out,
                "error": err,
            }
        )

    if len(contributions) != 6:
        raise RuntimeError(f"run_workstation must yield 6 contributions, got {len(contributions)}")
    ids = [c["fighter_id"] for c in contributions]
    if len(set(ids)) != 6:
        raise RuntimeError(f"run_workstation requires 6 distinct fighter ids, got {ids}")

    plan, patches, disagreements, next_actions = _synthesize(contributions, text_brief)

    # Context for a subsequent refine pass (slim) — includes all 6 prior outputs
    out_refine = {
        "brief": text_brief,
        "plan": plan,
        "patches": patches,
        "next_actions": next_actions,
        "disagreements": disagreements,
        "contributions": [
            {
                "role": c["role"],
                "fighter_id": c["fighter_id"],
                "lab": c["lab"],
                "mode": c["mode"],
                "text": c["text"][:800],
                "error": c.get("error"),
            }
            for c in contributions
        ],
        "role_map": role_map,
    }

    vision_note = {
        "vision_providers": sorted(VISION_PROVIDERS),
        "text_stub_only": ["deepseek"],
        "image_count": len(images),
        "attachment_meta": processed["meta"],
    }

    result: dict[str, Any] = {
        "ok": True,
        "product": "NEXUS AI Workstation",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "brief": text_brief,
        "used_default_brief": used_default,
        "contributions": contributions,
        "contribution_count": len(contributions),
        "plan": plan,
        "patches": patches,
        "disagreements": disagreements,
        "next_actions": next_actions,
        "refine_context": out_refine,
        "role_map": role_map,
        "rotation_index": (
            _rotation_index() if rotation_index is None else int(rotation_index)
        ),
        "live_count": sum(1 for c in contributions if c["mode"] == "LIVE"),
        "demo_count": sum(1 for c in contributions if c["mode"] == "DEMO"),
        "error_count": sum(1 for c in contributions if c.get("error")),
        "attachments": vision_note,
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
    "MAX_ATTACHMENTS_DECODED",
    "VISION_PROVIDERS",
    "AttachmentError",
    "ensure_full_roster",
    "assign_roles",
    "default_brief",
    "process_attachments",
    "run_workstation",
]
