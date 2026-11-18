"""Provider-neutral LLM port, adapter, fallback, and deterministic fake."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ConfigDict


class LLMRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    task: str
    prompt: str
    tenant_id: str
    run_id: str
    max_output_tokens: int = 2_048


class LLMResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float | None = None


class LLMPort(Protocol):
    async def complete(self, request: LLMRequest) -> LLMResponse: ...


ProviderCall = Callable[[LLMRequest], Awaitable[LLMResponse]]


@dataclass(slots=True)
class ProviderLLMAdapter:
    """Adapt a provider SDK call without coupling application code to its SDK."""

    provider_name: str
    call: ProviderCall

    async def complete(self, request: LLMRequest) -> LLMResponse:
        response = await self.call(request)
        if response.input_tokens < 0 or response.output_tokens < 0:
            raise ValueError("Provider returned negative token usage")
        return response.model_copy(update={"model": response.model or self.provider_name})


@dataclass(slots=True)
class FallbackLLM:
    primary: LLMPort
    fallback: LLMPort

    async def complete(self, request: LLMRequest) -> LLMResponse:
        try:
            return await self.primary.complete(request)
        except Exception:
            return await self.fallback.complete(request)


@dataclass(slots=True)
class FakeLLM:
    """Predictable local LLM fake; all usage is explicitly synthetic."""

    model: str = "fake-deterministic"
    fail: bool = False

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if self.fail:
            raise RuntimeError("Synthetic provider failure")
        if request.task == "classify":
            user_request = request.prompt.rsplit("User request:", maxsplit=1)[-1]
            lowered = user_request.casefold()
            routes = [
                agent
                for keyword, agent in (
                    ("stock", "inventory"),
                    ("inventory", "inventory"),
                    ("price", "pricing"),
                    ("competitor", "pricing"),
                    ("shipment", "logistics"),
                    ("delivery", "logistics"),
                    ("customer", "support"),
                    ("support", "support"),
                )
                if keyword in lowered
            ]
            unique_routes = list(dict.fromkeys(routes)) or ["support"]
            result = ",".join(unique_routes)
        else:
            result = f"{request.task}: {request.prompt.strip()}"
        return LLMResponse(
            text=result,
            model=self.model,
            input_tokens=max(1, len(request.prompt.split())),
            output_tokens=min(self._token_count(result), request.max_output_tokens),
            cost_usd=0,
        )

    @staticmethod
    def _token_count(text: str) -> int:
        return max(1, len(text.split()))
