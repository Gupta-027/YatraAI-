"""LLM provider abstraction.

The application must produce complete, validated itineraries and useful place
answers **with no LLM at all**. The LLM's job is narrow and late: reword content
that the deterministic pipeline has already computed and validated. Three
providers implement one interface:

``MockProvider``  (default)  Deterministic template composition. No network, no
                             key, no cost. Used in tests and CI, and is the
                             automatic fallback when a real provider fails.
``AnthropicProvider``        Claude via the official SDK.
``GeminiProvider``           Google Gemini.

Every real provider wraps its call in a timeout and falls back to the mock
rather than raising, and the response records which provider actually answered
so the UI can say "explanations are template-generated right now".
"""

from __future__ import annotations

import functools
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from yatraai.config import get_settings
from yatraai.core.security import neutralize_prompt_injection
from yatraai.core.telemetry import track
from yatraai.logging_config import get_logger

log = get_logger(__name__)

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-5",
    "gemini": "gemini-2.0-flash",
}


@dataclass
class LLMMessage:
    role: str  # "user" | "assistant"
    content: str


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    is_fallback: bool = False
    latency_ms: float = 0.0
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str = "stop"
    meta: dict = field(default_factory=dict)


class LLMProvider(ABC):
    name: str = "base"
    is_fallback: bool = False

    @abstractmethod
    def complete(
        self,
        *,
        system: str,
        messages: list[LLMMessage],
        max_tokens: int = 1000,
        temperature: float = 0.2,
    ) -> LLMResponse: ...


# --------------------------------------------------------------------------- #
class MockProvider(LLMProvider):
    """Deterministic composition. Never fabricates - it only rearranges input.

    This is what makes "the app works without an LLM" true rather than aspirational.
    Given a prompt whose context section already contains the validated facts, it
    emits a readable paragraph built from those facts and nothing else.
    """

    name = "mock"
    is_fallback = True
    model = "template-composer-v1"

    _CONTEXT_RE = re.compile(r"<context>(.*?)</context>", re.DOTALL | re.IGNORECASE)
    _SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

    def complete(
        self,
        *,
        system: str,
        messages: list[LLMMessage],
        max_tokens: int = 1000,
        temperature: float = 0.2,
    ) -> LLMResponse:
        del system, temperature
        with track("llm", self.name, "complete") as state:
            state["fallback_used"] = True
            prompt = "\n".join(m.content for m in messages if m.role == "user")
            context_blocks = self._CONTEXT_RE.findall(prompt)

            if context_blocks:
                text = self._compose_from_context(context_blocks)
            else:
                text = (
                    "A language model is not configured, so this response is generated from "
                    "the structured data the planner already validated."
                )

            words = text.split()
            if len(words) > max_tokens:
                text = " ".join(words[:max_tokens]) + "..."

            return LLMResponse(
                text=text,
                provider=self.name,
                model=self.model,
                is_fallback=True,
                finish_reason="stop",
                meta={"note": "template-composed from retrieved context; no model called"},
            )

    def _compose_from_context(self, blocks: list[str]) -> str:
        sentences: list[str] = []
        seen: set[str] = set()
        for block in blocks:
            for raw in self._SENTENCE_RE.split(block.strip()):
                sentence = " ".join(raw.split())
                if len(sentence) < 25 or sentence.startswith(("##", "[", "-")):
                    continue
                key = sentence[:60].lower()
                if key in seen:
                    continue
                seen.add(key)
                sentences.append(sentence if sentence.endswith((".", "!", "?")) else sentence + ".")
                if len(sentences) >= 6:
                    break
            if len(sentences) >= 6:
                break
        return " ".join(sentences) if sentences else "No supporting detail was retrieved."


# --------------------------------------------------------------------------- #
class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str | None, timeout: float) -> None:
        import anthropic

        self.model = model or DEFAULT_MODELS["anthropic"]
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
        self._fallback = MockProvider()

    def complete(
        self,
        *,
        system: str,
        messages: list[LLMMessage],
        max_tokens: int = 1000,
        temperature: float = 0.2,
    ) -> LLMResponse:
        with track("llm", self.name, "complete") as state:
            try:
                response = self._client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system,
                    messages=[{"role": m.role, "content": m.content} for m in messages],
                )
                text = "".join(
                    block.text for block in response.content if getattr(block, "type", "") == "text"
                )
                return LLMResponse(
                    text=text.strip(),
                    provider=self.name,
                    model=self.model,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    finish_reason=response.stop_reason or "stop",
                )
            except Exception as exc:
                state["ok"] = False
                state["fallback_used"] = True
                state["error_kind"] = type(exc).__name__
                log.warning("llm.anthropic_failed", error=str(exc))
                fallback = self._fallback.complete(
                    system=system, messages=messages, max_tokens=max_tokens
                )
                fallback.meta["upstream_error"] = type(exc).__name__
                return fallback


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str | None, timeout: float) -> None:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        self.model = model or DEFAULT_MODELS["gemini"]
        self._genai = genai
        self._timeout = timeout
        self._fallback = MockProvider()

    def complete(
        self,
        *,
        system: str,
        messages: list[LLMMessage],
        max_tokens: int = 1000,
        temperature: float = 0.2,
    ) -> LLMResponse:
        with track("llm", self.name, "complete") as state:
            try:
                model = self._genai.GenerativeModel(self.model, system_instruction=system)
                prompt = "\n\n".join(m.content for m in messages)
                response = model.generate_content(
                    prompt,
                    generation_config={
                        "max_output_tokens": max_tokens,
                        "temperature": temperature,
                    },
                    request_options={"timeout": self._timeout},
                )
                return LLMResponse(
                    text=(response.text or "").strip(),
                    provider=self.name,
                    model=self.model,
                )
            except Exception as exc:
                state["ok"] = False
                state["fallback_used"] = True
                state["error_kind"] = type(exc).__name__
                log.warning("llm.gemini_failed", error=str(exc))
                fallback = self._fallback.complete(
                    system=system, messages=messages, max_tokens=max_tokens
                )
                fallback.meta["upstream_error"] = type(exc).__name__
                return fallback


# --------------------------------------------------------------------------- #
@functools.lru_cache(maxsize=1)
def get_llm_provider() -> LLMProvider:
    s = get_settings()
    try:
        if s.llm_provider == "anthropic" and s.anthropic_api_key:
            return AnthropicProvider(s.anthropic_api_key, s.llm_model, s.llm_timeout_seconds)
        if s.llm_provider == "gemini" and s.gemini_api_key:
            return GeminiProvider(s.gemini_api_key, s.llm_model, s.llm_timeout_seconds)
    except Exception as exc:
        log.warning("llm.provider_init_failed", provider=s.llm_provider, error=str(exc))
    if s.llm_provider != "mock":
        log.warning(
            "llm.falling_back_to_mock",
            requested=s.llm_provider,
            reason="missing API key or SDK not installed",
        )
    return MockProvider()


def reset_llm_cache() -> None:
    get_llm_provider.cache_clear()


def safe_context(text: str, *, max_chars: int = 12000) -> str:
    """Prepare untrusted retrieved text for inclusion in a prompt.

    Retrieved documents are data, not instructions. Instruction-shaped spans are
    neutralised before the text ever reaches a model.
    """
    return neutralize_prompt_injection(text or "")[:max_chars]
