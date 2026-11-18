"""Google Gemini Developer API adapter with environment-driven key fallback."""

from dataclasses import dataclass

from google import genai
from google.genai import types

from clos.application.llm import LLMPort, LLMRequest, LLMResponse


class GeminiProviderUnavailable(RuntimeError):
    """Every configured Gemini key failed; no provider detail or secret is exposed."""


def minimize_prompt(prompt: str) -> str:
    """Remove common direct identifiers and credential-shaped strings before provider calls."""
    import re

    redactions = (
        (re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE), "[EMAIL]"),
        (re.compile(r"(?<!\w)(?:\+?\d[\d .()/-]{7,}\d)(?!\w)"), "[PHONE_OR_NUMBER]"),
        (
            re.compile(r"(?i)\b(?:api[_ -]?key|token|password|secret)\s*[:=]\s*\S+"),
            "[CREDENTIAL]",
        ),
    )
    minimized = prompt
    for pattern, replacement in redactions:
        minimized = pattern.sub(replacement, minimized)
    return minimized


@dataclass(slots=True)
class GeminiAPIAdapter:
    client: genai.Client
    model: str

    async def complete(self, request: LLMRequest) -> LLMResponse:
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=minimize_prompt(request.prompt),
            config=types.GenerateContentConfig(
                max_output_tokens=request.max_output_tokens,
                temperature=0,
            ),
        )
        usage = response.usage_metadata
        input_tokens = getattr(usage, "prompt_token_count", None)
        output_tokens = getattr(usage, "candidates_token_count", None)
        if input_tokens is None or output_tokens is None:
            raise RuntimeError("Gemini did not return token usage metadata")
        if response.text is None:
            raise RuntimeError("Gemini returned no text content")
        return LLMResponse(
            text=response.text,
            model=getattr(response, "model_version", None) or self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=None,
        )

    async def aclose(self) -> None:
        await self.client.aio.aclose()


@dataclass(slots=True)
class KeyFallbackLLM:
    """Try configured Gemini keys in order and fail without exposing credentials."""

    providers: tuple[LLMPort, ...]

    def __post_init__(self) -> None:
        if not self.providers:
            raise ValueError("At least one Gemini provider key is required")

    async def complete(self, request: LLMRequest) -> LLMResponse:
        for provider in self.providers:
            try:
                return await provider.complete(request)
            except Exception:
                continue
        raise GeminiProviderUnavailable(
            f"All {len(self.providers)} configured Gemini keys failed"
        ) from None

    async def aclose(self) -> None:
        for provider in self.providers:
            close = getattr(provider, "aclose", None)
            if close is not None:
                await close()


def build_gemini_llm(api_keys: list[str], model: str) -> KeyFallbackLLM:
    keys = list(dict.fromkeys(key.strip() for key in api_keys if key.strip()))
    return KeyFallbackLLM(
        tuple(GeminiAPIAdapter(genai.Client(api_key=key), model=model) for key in keys)
    )
