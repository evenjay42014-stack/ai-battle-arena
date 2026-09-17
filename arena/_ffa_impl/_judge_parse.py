"""FFA engine: _judge_parse."""
from arena._ffa_impl.common import *  # noqa: F403
from arena._ffa_impl._elo import *  # noqa: F403

def _parse_judge_json_multi(text: str, fighter_ids: list[str]) -> list[str] | None:
    """Parse judge JSON into ranked fighter id list (best first)."""
    m = re.search(r"\{.*\}", text.strip(), re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        # try smaller object
        m2 = re.search(r"\{[^{}]*\}", text.strip(), re.DOTALL)
        if not m2:
            return None
        try:
            data = json.loads(m2.group(0))
        except json.JSONDecodeError:
            return None

    if "ranking" in data and isinstance(data["ranking"], list):
        ranking = [str(x).strip() for x in data["ranking"]]
        # Map labels A/B/C/D or indices to ids
        mapped: list[str] = []
        for item in ranking:
            low = item.lower()
            if item in fighter_ids:
                mapped.append(item)
            elif low in ("a", "1") and len(fighter_ids) > 0:
                mapped.append(fighter_ids[0])
            elif low in ("b", "2") and len(fighter_ids) > 1:
                mapped.append(fighter_ids[1])
            elif low in ("c", "3") and len(fighter_ids) > 2:
                mapped.append(fighter_ids[2])
            elif low in ("d", "4") and len(fighter_ids) > 3:
                mapped.append(fighter_ids[3])
            else:
                for fid in fighter_ids:
                    if fid.lower() in low or low in fid.lower():
                        mapped.append(fid)
                        break
        # Dedupe preserve order, append missing
        seen: set[str] = set()
        out: list[str] = []
        for fid in mapped:
            if fid in fighter_ids and fid not in seen:
                out.append(fid)
                seen.add(fid)
        for fid in fighter_ids:
            if fid not in seen:
                out.append(fid)
        return out if out else None

    # score_* keys
    scores: list[tuple[str, float]] = []
    for i, fid in enumerate(fighter_ids):
        key_opts = [f"score_{fid}", f"score_{chr(ord('a') + i)}", f"s{i}"]
        val = None
        for k in key_opts:
            if k in data:
                val = float(data[k])
                break
        if val is None and "scores" in data and isinstance(data["scores"], dict):
            if fid in data["scores"]:
                val = float(data["scores"][fid])
        if val is None:
            return None
        scores.append((fid, val))
    scores.sort(key=lambda x: (-x[1], x[0]))
    return [fid for fid, _ in scores]


def live_judge(
    prompt: str,
    ans_a: str,
    ans_b: str,
    protocol: Protocol,
    *,
    exclude_providers: list[str] | None = None,
) -> tuple[float, float, str, bool]:
    """Legacy 1v1 judge (kept for fight_once compat)."""
    order, note, live = live_judge_n(
        prompt,
        {"A": ans_a, "B": ans_b},
        protocol,
        exclude_providers=exclude_providers,
        prefer_providers=None,
        system_seed="legacy",
    )
    # Map A/B ranking to scores
    if order[0] == "A" and order[1] == "B":
        return 1.0, 0.0, note, live
    if order[0] == "B" and order[1] == "A":
        return 0.0, 1.0, note, live
    return 0.5, 0.5, note, live


def live_judge_n(
    prompt: str,
    answers: dict[str, str],
    protocol: Protocol,
    *,
    exclude_providers: list[str] | None = None,
    prefer_providers: list[str] | None = None,
    system_seed: str = "alpha",
) -> tuple[list[str], str, bool]:
    """Judge N fighters. Returns (ranking best-first, note, live_ok)."""
    fighter_ids = list(answers.keys())
    labels = "ABCD"
    label_map = {labels[i]: fid for i, fid in enumerate(fighter_ids) if i < 4}
    system = (
        f"Arena FFA judge seed={system_seed}. Rank by correctness+constraints NOT length. "
        f'JSON only: {{"ranking":["id1","id2",...]}} best-first. '
        f"Fighters: {fighter_ids}. You may use labels {list(label_map)} mapped to ids."
    )
    parts = [f"{protocol.id}/{protocol.axis}", f"Q:{prompt[:700]}"]
    for i, fid in enumerate(fighter_ids):
        lab = labels[i] if i < len(labels) else str(i)
        parts.append(f"{lab}({fid}):{answers[fid][:700]}")
    user = "\n".join(parts)

    prefer = prefer_providers or ["openrouter", "openai", "google", "anthropic", "deepseek", "xai"]
    if exclude_providers:
        prefer = [p for p in prefer if p not in exclude_providers] + list(exclude_providers)

    text, route = chat_completion_any(user, system=system, prefer_providers=prefer)
    if not text:
        order, _raw, note = _heuristic_rank(prompt, answers, protocol)
        return order, f"fallback:{note}", False
    parsed = _parse_judge_json_multi(text, fighter_ids)
    if not parsed:
        order, _raw, note = _heuristic_rank(prompt, answers, protocol)
        return order, f"parse_fail:{route}:{note}", False
    return parsed, f"live_judge:{route}:seed={system_seed}", True

__all__ = ['_parse_judge_json_multi', 'live_judge', 'live_judge_n']
