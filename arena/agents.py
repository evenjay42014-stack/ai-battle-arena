"""Fighters: demo personas or live API-backed agents."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

DEMO_PERSONAS: list[dict[str, Any]] = [
    {
        "id": "grok-4.6",
        "lab": "xAI",
        "provider": "xai",
        "spike": "reasoning",
        "hole": "instruction",
        "style": "blunt, speculative, metacognitive",
    },
    {
        "id": "claude-fable-5",
        "lab": "Anthropic",
        "provider": "anthropic",
        "spike": "instruction",
        "hole": "planning",
        "style": "careful, structured, over-refuses edge cases",
    },
    {
        "id": "gpt-6-astra",
        "lab": "OpenAI",
        "provider": "openai",
        "spike": "coding",
        "hole": "knowledge",
        "style": "fluent planner that sometimes invents citations",
    },
    {
        "id": "gemini-3-ultra",
        "lab": "Google",
        "provider": "google",
        "spike": "memory",
        "hole": "robustness",
        "style": "broad knowledge, brittle under inverse probes",
    },
    {
        "id": "deepseek-v4",
        "lab": "DeepSeek",
        "provider": "deepseek",
        "spike": "reasoning",
        "hole": "robustness",
        "style": "strong coder, soft on adversarial framing",
    },
    {
        "id": "llama-4-maverick",
        "lab": "Meta",
        "provider": "openrouter",
        "spike": "instruction",
        "hole": "knowledge",
        "style": "obedient, playbook-hungry, thin on obscure facts",
    },
]

_PROVIDER_ENV: dict[str, list[str]] = {
    "openrouter": ["OPENROUTER_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
    "anthropic": ["ANTHROPIC_API_KEY"],
    "google": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
    "xai": ["XAI_API_KEY"],
}

_OPENROUTER_MODELS: dict[str, str] = {
    "xai": "x-ai/grok-beta",
    "anthropic": "anthropic/claude-3.5-haiku",
    "openai": "openai/gpt-4o-mini",
    "google": "google/gemini-flash-1.5",
    "deepseek": "deepseek/deepseek-chat",
    "openrouter": "openrouter/auto",
}


def _env_key(names: list[str]) -> str:
    for n in names:
        v = (os.environ.get(n) or "").strip()
        if v:
            return v
    return ""


@dataclass
class Fighter:
    id: str
    lab: str
    provider: str
    spike: str = ""
    hole: str = ""
    style: str = ""
    mode: str = "DEMO"  # DEMO | LIVE
    wins: int = 0
    losses: int = 0
    elo: float = 1500.0
    meta: dict[str, Any] = field(default_factory=dict)

    def label(self) -> str:
        return f"[{self.mode}] {self.id}"

    def answer(self, prompt: str) -> str:
        """Demo policy: deterministic persona-flavored reply."""
        tip = f"(spike={self.spike}, hole={self.hole})"
        return (
            f"{self.id} [{self.mode}] {self.style}. "
            f"On: {prompt[:120]}… {tip}"
        )


class LiveFighter(Fighter):
    """Calls OpenRouter when available, else matching direct provider."""

    def answer(self, prompt: str) -> str:
        or_key = _env_key(["OPENROUTER_API_KEY"])
        if or_key:
            text = self._chat_openrouter(or_key, prompt)
            if text is not None:
                return text
        direct = self._chat_direct(prompt)
        if direct is not None:
            return direct
        # Fall back to demo-style reply without flipping mode mid-fight.
        return super().answer(prompt) + " [live call failed → demo fallback]"

    def _chat_openrouter(self, key: str, prompt: str) -> str | None:
        model = _OPENROUTER_MODELS.get(self.provider, "openrouter/auto")
        return _openai_compat(
            "https://openrouter.ai/api/v1/chat/completions",
            key,
            model,
            prompt,
            extra_headers={
                "HTTP-Referer": "https://github.com/local/ai-battle-arena",
                "X-Title": "NEXUS AI Battle Arena",
            },
        )

    def _chat_direct(self, prompt: str) -> str | None:
        p = self.provider
        if p == "openai":
            key = _env_key(["OPENAI_API_KEY"])
            if not key:
                return None
            return _openai_compat(
                "https://api.openai.com/v1/chat/completions",
                key,
                "gpt-4o-mini",
                prompt,
            )
        if p == "deepseek":
            key = _env_key(["DEEPSEEK_API_KEY"])
            if not key:
                return None
            return _openai_compat(
                "https://api.deepseek.com/chat/completions",
                key,
                "deepseek-chat",
                prompt,
            )
        if p == "xai":
            key = _env_key(["XAI_API_KEY"])
            if not key:
                return None
            return _openai_compat(
                "https://api.x.ai/v1/chat/completions",
                key,
                "grok-4.6",
                prompt,
            )
        if p == "anthropic":
            return _anthropic_chat(prompt)
        if p == "google":
            return _google_chat(prompt)
        if p == "openrouter":
            key = _env_key(["OPENROUTER_API_KEY"])
            if not key:
                return None
            return self._chat_openrouter(key, prompt)
        return None


def _openai_compat(
    url: str,
    key: str,
    model: str,
    prompt: str,
    *,
    extra_headers: dict[str, str] | None = None,
) -> str | None:
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 256,
    }
    try:
        req = urllib.request.Request(
            url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        choices = data.get("choices") or []
        if not choices:
            return None
        msg = choices[0].get("message") or {}
        return (msg.get("content") or "").strip() or None
    except Exception:  # noqa: BLE001
        return None


def _anthropic_chat(prompt: str) -> str | None:
    key = _env_key(["ANTHROPIC_API_KEY"])
    if not key:
        return None
    body = {
        "model": "claude-3-5-haiku-latest",
        "max_tokens": 256,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    try:
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        parts = data.get("content") or []
        texts = [p.get("text", "") for p in parts if isinstance(p, dict)]
        out = "\n".join(t for t in texts if t).strip()
        return out or None
    except Exception:  # noqa: BLE001
        return None


def _google_chat(prompt: str) -> str | None:
    key = _env_key(["GOOGLE_API_KEY", "GEMINI_API_KEY"])
    if not key:
        return None
    model = "gemini-2.5-flash"
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={key}"
    )
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        cands = data.get("candidates") or []
        if not cands:
            return None
        parts = ((cands[0].get("content") or {}).get("parts")) or []
        texts = [p.get("text", "") for p in parts if isinstance(p, dict)]
        out = "\n".join(t for t in texts if t).strip()
        return out or None
    except Exception:  # noqa: BLE001
        return None


def provider_has_key(provider: str) -> bool:
    names = _PROVIDER_ENV.get(provider, [])
    return bool(_env_key(names)) or (
        provider != "openrouter" and bool(_env_key(["OPENROUTER_API_KEY"]))
    )


def build_roster(*, prefer_live: bool = True) -> list[Fighter]:
    """Build fighters; LIVE when a usable key exists for that provider (or OpenRouter)."""
    roster: list[Fighter] = []
    or_key = bool(_env_key(["OPENROUTER_API_KEY"]))
    for p in DEMO_PERSONAS:
        has_direct = bool(_env_key(_PROVIDER_ENV.get(p["provider"], [])))
        live = prefer_live and (or_key or has_direct)
        cls = LiveFighter if live else Fighter
        mode = "LIVE" if live else "DEMO"
        roster.append(
            cls(
                id=p["id"],
                lab=p["lab"],
                provider=p["provider"],
                spike=p["spike"],
                hole=p["hole"],
                style=p["style"],
                mode=mode,
            )
        )
    return roster
