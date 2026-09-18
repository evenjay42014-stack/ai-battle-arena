"""Fighters: demo personas or live API-backed agents."""

from __future__ import annotations

import json
import os
import re
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

# Direct (native) model IDs — keep in sync with arena/live.py probes.
_DIRECT_MODELS: dict[str, list[str]] = {
    "xai": ["grok-4.6", "grok-4.5", "grok-4.3"],
    "openai": ["gpt-4o-mini", "gpt-4.1-mini"],
    "anthropic": [
        "claude-haiku-4-5-20251001",
        "claude-sonnet-4-5-20250929",
        "claude-3-haiku-20240307",
    ],
    "google": ["gemini-3.6-flash", "gemini-flash-latest", "gemini-3-flash-preview"],
    "deepseek": ["deepseek-chat", "deepseek-flash"],
}

# OpenRouter fallbacks (used after direct fails, or as Meta's primary).
_OPENROUTER_MODELS: dict[str, list[str]] = {
    "xai": ["x-ai/grok-4", "x-ai/grok-3", "x-ai/grok-2"],
    "anthropic": [
        "anthropic/claude-haiku-4.5",
        "anthropic/claude-3.5-haiku",
        "anthropic/claude-3-haiku",
    ],
    "openai": ["openai/gpt-4o-mini", "openai/gpt-4.1-mini"],
    "google": ["google/gemini-3.6-flash", "google/gemini-3-flash-preview", "google/gemini-2.5-flash"],
    "deepseek": ["deepseek/deepseek-chat", "deepseek/deepseek-v3.2"],
    "openrouter": [
        "meta-llama/llama-4-maverick",
        "meta-llama/llama-3.3-70b-instruct",
        "meta-llama/llama-3.1-8b-instruct",
    ],
}


def _env_key(names: list[str]) -> str:
    for n in names:
        v = (os.environ.get(n) or "").strip()
        if v:
            return v
    return ""


def _redact(detail: str) -> str:
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
    # Also redact bare bearer-looking tokens if they leaked into messages.
    detail = re.sub(r"(sk-[A-Za-z0-9_-]{8,})", "[REDACTED]", detail)
    detail = re.sub(r"(xai-[A-Za-z0-9_-]{8,})", "[REDACTED]", detail)
    return detail


def _compose_user(prompt: str, playbook_context: str | None) -> str:
    if playbook_context and playbook_context.strip():
        return f"{playbook_context.strip()}\n\n---\nTASK:\n{prompt}"
    return prompt


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

    def answer(
        self,
        prompt: str,
        *,
        playbook_context: str | None = None,
        system: str | None = None,
        images: list[dict[str, Any]] | None = None,
    ) -> str:
        """Demo policy: deterministic persona-flavored reply."""
        tip = f"(spike={self.spike}, hole={self.hole})"
        sys_bit = f" sys={system[:60]}…" if system else ""
        pb = " with-playbook" if playbook_context else ""
        img = f" images={len(images)}" if images else ""
        return (
            f"{self.id} [{self.mode}]{pb}{sys_bit}{img} {self.style}. "
            f"On: {prompt[:120]}… {tip}"
        )


class LiveFighter(Fighter):
    """Calls each lab's frontier API first when that key exists; OpenRouter fallback."""

    def answer(
        self,
        prompt: str,
        *,
        playbook_context: str | None = None,
        system: str | None = None,
        images: list[dict[str, Any]] | None = None,
    ) -> str:
        user = _compose_user(prompt, playbook_context)
        errors: list[str] = []

        # 1) Native frontier API for this provider (Meta/openrouter skips — no native key).
        direct = self._chat_direct(user, system=system, errors=errors, images=images)
        if direct is not None:
            return direct

        # 2) OpenRouter fallback (primary for Meta).
        or_key = _env_key(["OPENROUTER_API_KEY"])
        if or_key:
            text = self._chat_openrouter(
                or_key, user, system=system, errors=errors, images=images
            )
            if text is not None:
                return text
        elif self.provider == "openrouter":
            errors.append("OPENROUTER_API_KEY not set")

        detail = "; ".join(errors) if errors else "no provider route succeeded"
        return (
            f"[LIVE ERROR] {self.id} ({self.provider}): "
            f"{_redact(detail)}"
        )

    def _chat_openrouter(
        self,
        key: str,
        prompt: str,
        *,
        system: str | None = None,
        errors: list[str] | None = None,
        images: list[dict[str, Any]] | None = None,
    ) -> str | None:
        models = _OPENROUTER_MODELS.get(self.provider, ["openrouter/auto"])
        last_err = ""
        for model in models:
            text, err = _openai_compat(
                "https://openrouter.ai/api/v1/chat/completions",
                key,
                model,
                prompt,
                system=system,
                images=images,
                extra_headers={
                    "HTTP-Referer": "https://github.com/local/ai-battle-arena",
                    "X-Title": "NEXUS AI Battle Arena",
                },
            )
            if text is not None:
                return text
            last_err = err or "unknown"
            if "model" in last_err.lower() or "404" in last_err:
                continue
            break
        if errors is not None:
            errors.append(f"openrouter:{last_err}")
        return None

    def _chat_direct(
        self,
        prompt: str,
        *,
        system: str | None = None,
        errors: list[str] | None = None,
        images: list[dict[str, Any]] | None = None,
    ) -> str | None:
        p = self.provider
        if p == "openai":
            key = _env_key(["OPENAI_API_KEY"])
            if not key:
                if errors is not None:
                    errors.append("openai:OPENAI_API_KEY not set")
                return None
            return self._try_openai_compat_models(
                "https://api.openai.com/v1/chat/completions",
                key,
                _DIRECT_MODELS["openai"],
                prompt,
                system=system,
                route="openai",
                errors=errors,
                images=images,
            )
        if p == "deepseek":
            key = _env_key(["DEEPSEEK_API_KEY"])
            if not key:
                if errors is not None:
                    errors.append("deepseek:DEEPSEEK_API_KEY not set")
                return None
            # DeepSeek chat typically has no vision — omit images (text stub in brief).
            return self._try_openai_compat_models(
                "https://api.deepseek.com/chat/completions",
                key,
                _DIRECT_MODELS["deepseek"],
                prompt,
                system=system,
                route="deepseek",
                errors=errors,
                images=None,
            )
        if p == "xai":
            key = _env_key(["XAI_API_KEY"])
            if not key:
                if errors is not None:
                    errors.append("xai:XAI_API_KEY not set")
                return None
            return self._try_openai_compat_models(
                "https://api.x.ai/v1/chat/completions",
                key,
                _DIRECT_MODELS["xai"],
                prompt,
                system=system,
                route="xai",
                errors=errors,
                images=images,
            )
        if p == "anthropic":
            return _anthropic_chat(prompt, system=system, errors=errors, images=images)
        if p == "google":
            return _google_chat(prompt, system=system, errors=errors, images=images)
        if p == "openrouter":
            # Meta: native path is OpenRouter only (handled by caller after direct).
            return None
        return None

    def _try_openai_compat_models(
        self,
        url: str,
        key: str,
        models: list[str],
        prompt: str,
        *,
        system: str | None,
        route: str,
        errors: list[str] | None,
        images: list[dict[str, Any]] | None = None,
    ) -> str | None:
        last_err = ""
        for model in models:
            text, err = _openai_compat(
                url, key, model, prompt, system=system, images=images
            )
            if text is not None:
                return text
            last_err = err or "unknown"
            if "model" in last_err.lower() or "404" in last_err:
                continue
            break
        if errors is not None:
            errors.append(f"{route}:{last_err}")
        return None


def _user_content_openai(
    prompt: str, images: list[dict[str, Any]] | None
) -> Any:
    """OpenAI-compatible multimodal user content (string or parts list)."""
    if not images:
        return prompt
    parts: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for img in images[:6]:
        mime = (img.get("mime") or "image/png").split(";")[0].strip()
        b64 = img.get("data_b64") or ""
        if not b64:
            continue
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            }
        )
    return parts


def _openai_compat(
    url: str,
    key: str,
    model: str,
    prompt: str,
    *,
    system: str | None = None,
    extra_headers: dict[str, str] | None = None,
    max_tokens: int = 280,
    images: list[dict[str, Any]] | None = None,
) -> tuple[str | None, str]:
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    messages: list[dict[str, Any]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": _user_content_openai(prompt, images)})
    body = {"model": model, "messages": messages, "max_tokens": max_tokens}
    try:
        req = urllib.request.Request(
            url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        choices = data.get("choices") or []
        if not choices:
            return None, f"model={model} empty choices"
        msg = choices[0].get("message") or {}
        text = (msg.get("content") or "").strip()
        if not text:
            return None, f"model={model} empty content"
        return text, ""
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")[:300]
        return None, _redact(f"model={model} HTTP {e.code}: {raw}")
    except Exception as e:  # noqa: BLE001
        return None, _redact(f"model={model} {type(e).__name__}: {e}")


def _anthropic_user_content(
    prompt: str, images: list[dict[str, Any]] | None
) -> Any:
    if not images:
        return prompt
    parts: list[dict[str, Any]] = []
    for img in images[:6]:
        mime = (img.get("mime") or "image/png").split(";")[0].strip()
        b64 = img.get("data_b64") or ""
        if not b64:
            continue
        # Anthropic expects jpeg/png/gif/webp
        if mime == "image/jpg":
            mime = "image/jpeg"
        parts.append(
            {
                "type": "image",
                "source": {"type": "base64", "media_type": mime, "data": b64},
            }
        )
    parts.append({"type": "text", "text": prompt})
    return parts


def _anthropic_chat(
    prompt: str,
    *,
    system: str | None = None,
    errors: list[str] | None = None,
    images: list[dict[str, Any]] | None = None,
) -> str | None:
    key = _env_key(["ANTHROPIC_API_KEY"])
    if not key:
        if errors is not None:
            errors.append("anthropic:ANTHROPIC_API_KEY not set")
        return None
    last_err = ""
    for model in _DIRECT_MODELS["anthropic"]:
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": 280,
            "messages": [
                {"role": "user", "content": _anthropic_user_content(prompt, images)}
            ],
        }
        if system:
            body["system"] = system
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
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            parts = data.get("content") or []
            texts = [p.get("text", "") for p in parts if isinstance(p, dict)]
            out = "\n".join(t for t in texts if t).strip()
            if out:
                return out
            last_err = f"model={model} empty content"
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")[:300]
            last_err = _redact(f"model={model} HTTP {e.code}: {raw}")
            if e.code in (401, 403):
                break
            if "model" in raw.lower() or e.code == 404:
                continue
            break
        except Exception as e:  # noqa: BLE001
            last_err = _redact(f"model={model} {type(e).__name__}: {e}")
            break
    if errors is not None:
        errors.append(f"anthropic:{last_err or 'failed'}")
    return None


def _google_chat(
    prompt: str,
    *,
    system: str | None = None,
    errors: list[str] | None = None,
    images: list[dict[str, Any]] | None = None,
) -> str | None:
    key = _env_key(["GOOGLE_API_KEY", "GEMINI_API_KEY"])
    if not key:
        if errors is not None:
            errors.append("google:GOOGLE_API_KEY / GEMINI_API_KEY not set")
        return None
    last_err = ""
    for model in _DIRECT_MODELS["google"]:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={key}"
        )
        parts: list[dict[str, Any]] = [{"text": prompt}]
        if images:
            for img in images[:6]:
                mime = (img.get("mime") or "image/png").split(";")[0].strip()
                b64 = img.get("data_b64") or ""
                if not b64:
                    continue
                if mime == "image/jpg":
                    mime = "image/jpeg"
                parts.append({"inline_data": {"mime_type": mime, "data": b64}})
        body: dict[str, Any] = {"contents": [{"parts": parts}]}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            cands = data.get("candidates") or []
            if not cands:
                last_err = f"model={model} empty candidates"
                continue
            parts = ((cands[0].get("content") or {}).get("parts")) or []
            texts = [p.get("text", "") for p in parts if isinstance(p, dict)]
            out = "\n".join(t for t in texts if t).strip()
            if out:
                return out
            last_err = f"model={model} empty content"
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")[:300]
            last_err = _redact(f"model={model} HTTP {e.code}: {raw}")
            # 404/retired model, rate limit, or transient capacity — try next model
            if "model" in raw.lower() or e.code in (404, 429, 503):
                continue
            break
        except Exception as e:  # noqa: BLE001
            last_err = _redact(f"model={model} {type(e).__name__}: {e}")
            break
    if errors is not None:
        errors.append(f"google:{last_err or 'failed'}")
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


def chat_completion_any(
    prompt: str,
    *,
    system: str | None = None,
    prefer_providers: list[str] | None = None,
) -> tuple[str | None, str]:
    """Best-effort chat via first available direct provider, then OpenRouter.

    Returns (text, route_label). Used for LIVE judging.
    """
    prefer = prefer_providers or ["openai", "anthropic", "google", "xai", "deepseek", "openrouter"]
    for p in prefer:
        if p == "openrouter":
            continue
        if p == "openai":
            key = _env_key(["OPENAI_API_KEY"])
            if key:
                for model in _DIRECT_MODELS["openai"]:
                    text, _err = _openai_compat(
                        "https://api.openai.com/v1/chat/completions",
                        key,
                        model,
                        prompt,
                        system=system,
                        max_tokens=120,
                    )
                    if text:
                        return text, f"openai:{model}"
        elif p == "anthropic":
            text = _anthropic_chat(prompt, system=system)
            if text:
                return text, f"anthropic:{_DIRECT_MODELS['anthropic'][0]}"
        elif p == "google":
            text = _google_chat(prompt, system=system)
            if text:
                return text, f"google:{_DIRECT_MODELS['google'][0]}"
        elif p == "xai":
            key = _env_key(["XAI_API_KEY"])
            if key:
                for model in _DIRECT_MODELS["xai"]:
                    text, _err = _openai_compat(
                        "https://api.x.ai/v1/chat/completions",
                        key,
                        model,
                        prompt,
                        system=system,
                        max_tokens=120,
                    )
                    if text:
                        return text, f"xai:{model}"
        elif p == "deepseek":
            key = _env_key(["DEEPSEEK_API_KEY"])
            if key:
                for model in _DIRECT_MODELS["deepseek"]:
                    text, _err = _openai_compat(
                        "https://api.deepseek.com/chat/completions",
                        key,
                        model,
                        prompt,
                        system=system,
                        max_tokens=120,
                    )
                    if text:
                        return text, f"deepseek:{model}"
    or_key = _env_key(["OPENROUTER_API_KEY"])
    if "openrouter" in prefer and or_key:
        for model in ("openai/gpt-4o-mini", "openrouter/auto"):
            text, _err = _openai_compat(
                "https://openrouter.ai/api/v1/chat/completions",
                or_key,
                model,
                prompt,
                system=system,
                max_tokens=120,
                extra_headers={
                    "HTTP-Referer": "https://github.com/local/ai-battle-arena",
                    "X-Title": "NEXUS AI Battle Arena Judge",
                },
            )
            if text:
                return text, f"openrouter:{model}"
    return None, "none"
