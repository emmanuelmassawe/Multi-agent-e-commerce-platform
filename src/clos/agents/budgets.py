"""Hard per-run budgets shared by supervisor nodes and tools."""

from dataclasses import dataclass


class BudgetExceeded(RuntimeError):
    """Raised when a run reaches one of its configured hard limits."""


@dataclass(frozen=True, slots=True)
class BudgetLimits:
    max_tokens: int = 8_000
    max_steps: int = 24
    max_tool_calls: int = 16
    max_wall_seconds: float = 120.0

    def __post_init__(self) -> None:
        if min(self.max_tokens, self.max_steps, self.max_tool_calls) < 1:
            raise ValueError("Integer budget limits must be positive")
        if self.max_wall_seconds <= 0:
            raise ValueError("max_wall_seconds must be positive")


@dataclass(slots=True)
class BudgetUsage:
    tokens: int = 0
    steps: int = 0
    tool_calls: int = 0


class BudgetEnforcer:
    """Tracks budget consumption and hard-stops before limits can be exceeded."""

    def __init__(self, limits: BudgetLimits) -> None:
        self.limits = limits
        self.usage = BudgetUsage()

    def check_time(self, elapsed_seconds: float) -> None:
        if elapsed_seconds >= self.limits.max_wall_seconds:
            raise BudgetExceeded("Run exceeded its wall-clock budget")

    def record_step(self) -> None:
        self._consume("steps", 1, self.limits.max_steps, "step")

    def record_tool_call(self) -> None:
        self._consume("tool_calls", 1, self.limits.max_tool_calls, "tool-call")

    def record_tokens(self, tokens: int) -> None:
        if tokens < 0:
            raise ValueError("Token usage cannot be negative")
        self._consume("tokens", tokens, self.limits.max_tokens, "token")

    def _consume(self, field: str, amount: int, limit: int, label: str) -> None:
        next_value = getattr(self.usage, field) + amount
        if next_value > limit:
            raise BudgetExceeded(f"Run exceeded its {label} budget ({limit})")
        setattr(self.usage, field, next_value)
