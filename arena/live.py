"""Minimal live chat/completions probes via urllib (no third-party deps)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Callable

Timeout = 20

# Keep probe lists aligned with arena/agents.py _DIRECT_MODELS / OpenRouter fallbacks.
XAI_MODELS = ("grok-4.6", "grok-4.5", "grok-4.3")
OPENAI_MODELS = ("gpt-4o-mini", "gpt-4.1-mini")
ANTHROPIC_MODELS = (
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-5-20250929",
    "claude-3-haiku-20240307",
)
GOOGLE_MODELS = ("gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash")
DEEPSEEK_MODELS = ("deepseek-chat", "deepseek-flash")
OPENROUTER_MODELS = ("openrouter/auto", "openai/gpt-4o-mini")


def _redact(detail: str) -> str:
    """Strip accidental key-looking substrings from error text."""
    for name in (
        "OPENROUTER_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "DEEPSEEK_API_KEY",
        "XAI_API_KEY",
    ):
        val = os.environ.get(name, "")
        if val and len(val) > 8 and val in detail:
            detail = detail.replace(val, "[REDACTED]")
    return detail


def _http_json(
    url: str,
    *,
    method: str = "POST",
    headers: dict[str, str] | None = None,
    body: dict | None = None,
    timeout: float = Timeout,
) -> tuple[int, dict | str]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw[:200]
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw[:300]
        return e.code, parsed
    except Exception as e:  # noqa: BLE001 — surface network failures as detail
        return -1, _redact(f"{type(e).__name__}: {e}")


def _key(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def check_openrouter() -> tuple[bool, str]:
    key = _key("OPENROUTER_API_KEY")
    if not key:
        return False, "OPENROUTER_API_KEY not set"
    for model in OPENROUTER_MODELS:
        status, payload = _http_json(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "HTTP-Referer": "https://github.com/local/ai-battle-arena",
                "X-Title": "NEXUS AI Battle Arena",
            },
            body={
                "model": model,
                "messages": [{"role": "user", "content": "Reply with OK"}],
                "max_tokens": 8,
            },
        )
        if status == 200 and isinstance(payload, dict) and payload.get("choices"):
            return True, f"ok model={model}"
        detail = payload if isinstance(payload, str) else json.dumps(payload)[:240]
        if status in (400, 404) and "model" in str(detail).lower():
            continue
        return False, _redact(f"HTTP {status}: {detail}")
    return False, "no working OpenRouter model"


def check_openai() -> tuple[bool, str]:
    key = _key("OPENAI_API_KEY")
    if not key:
        return False, "OPENAI_API_KEY not set"
    last_status, last_payload = -1, ""
    for model in OPENAI_MODELS:
        status, payload = _http_json(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            body={
                "model": model,
                "messages": [{"role": "user", "content": "Reply with OK"}],
                "max_tokens": 8,
            },
        )
        last_status, last_payload = status, payload
        if status == 200 and isinstance(payload, dict) and payload.get("choices"):
            return True, f"ok model={model}"
        detail = payload if isinstance(payload, str) else json.dumps(payload)
        if status in (400, 404) and "model" in str(detail).lower():
            continue
        break
    detail = last_payload if isinstance(last_payload, str) else json.dumps(last_payload)[:240]
    return False, _redact(f"HTTP {last_status}: {detail}")


def check_anthropic() -> tuple[bool, str]:
    key = _key("ANTHROPIC_API_KEY")
    if not key:
        return False, "ANTHROPIC_API_KEY not set"
    last_status, last_payload = -1, ""
    for model in ANTHROPIC_MODELS:
        status, payload = _http_json(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
            },
            body={
                "model": model,
                "max_tokens": 16,
                "messages": [{"role": "user", "content": "Reply with OK"}],
            },
        )
        last_status, last_payload = status, payload
        if status == 200 and isinstance(payload, dict) and payload.get("content"):
            return True, f"ok model={model}"
        detail = payload if isinstance(payload, str) else json.dumps(payload)
        if status in (401, 403) or "credit" in detail.lower() or "balance" in detail.lower():
            break
    detail = last_payload if isinstance(last_payload, str) else json.dumps(last_payload)[:240]
    return False, _redact(f"HTTP {last_status}: {detail}")


def check_google() -> tuple[bool, str]:
    key = _key("GOOGLE_API_KEY") or _key("GEMINI_API_KEY")
    if not key:
        return False, "GOOGLE_API_KEY / GEMINI_API_KEY not set"
    last_status, last_payload = -1, ""
    for model in GOOGLE_MODELS:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={key}"
        )
        status, payload = _http_json(
            url,
            body={"contents": [{"parts": [{"text": "Reply with OK"}]}]},
        )
        last_status, last_payload = status, payload
        if status == 200 and isinstance(payload, dict) and payload.get("candidates"):
            return True, f"ok model={model}"
    detail = last_payload if isinstance(last_payload, str) else json.dumps(last_payload)[:240]
    return False, _redact(f"HTTP {last_status}: {detail}")


def check_deepseek() -> tuple[bool, str]:
    key = _key("DEEPSEEK_API_KEY")
    if not key:
        return False, "DEEPSEEK_API_KEY not set"
    last_status, last_payload = -1, ""
    for model in DEEPSEEK_MODELS:
        status, payload = _http_json(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            body={
                "model": model,
                "messages": [{"role": "user", "content": "Reply with OK"}],
                "max_tokens": 8,
            },
        )
        last_status, last_payload = status, payload
        if status == 200 and isinstance(payload, dict) and payload.get("choices"):
            return True, f"ok model={model}"
        detail = payload if isinstance(payload, str) else json.dumps(payload)
        if status in (400, 404) and "model" in str(detail).lower():
            continue
        break
    detail = last_payload if isinstance(last_payload, str) else json.dumps(last_payload)[:240]
    return False, _redact(f"HTTP {last_status}: {detail}")


def check_xai() -> tuple[bool, str]:
    key = _key("XAI_API_KEY")
    if not key:
        return False, "XAI_API_KEY not set"
    last_status, last_payload = -1, ""
    for model in XAI_MODELS:
        status, payload = _http_json(
            "https://api.x.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            body={
                "model": model,
                "messages": [{"role": "user", "content": "Reply with OK"}],
                "max_tokens": 8,
            },
        )
        last_status, last_payload = status, payload
        if status == 200 and isinstance(payload, dict) and payload.get("choices"):
            return True, f"ok model={model}"
    detail = last_payload if isinstance(last_payload, str) else json.dumps(last_payload)[:240]
    return False, _redact(f"HTTP {last_status}: {detail}")


PROVIDERS: list[tuple[str, Callable[[], tuple[bool, str]]]] = [
    ("openrouter", check_openrouter),
    ("openai", check_openai),
    ("anthropic", check_anthropic),
    ("google", check_google),
    ("deepseek", check_deepseek),
    ("xai", check_xai),
]


def run_live_checks() -> list[tuple[str, bool, str]]:
    """Return [(name, ok, detail), ...] for each provider."""
    results: list[tuple[str, bool, str]] = []
    for name, fn in PROVIDERS:
        try:
            ok, detail = fn()
        except Exception as e:  # noqa: BLE001
            ok, detail = False, _redact(f"{type(e).__name__}: {e}")
        results.append((name, ok, detail))
    return results
