"""Provider-neutral LLM request/response DTOs and application port."""

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class LLMRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    task: str
    prompt: str
    tenant_id: str
    run_id: str
    max_output_tokens: int = Field(default=2_048, ge=1)


class LLMResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    model: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_usd: float | None = Field(default=None, ge=0)


class LLMPort(Protocol):
    async def complete(self, request: LLMRequest) -> LLMResponse: ...
