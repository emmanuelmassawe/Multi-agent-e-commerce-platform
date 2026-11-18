"""Identity roles and autonomy policies."""

from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    MANAGER = "manager"
    AGENT_OPERATOR = "agent-operator"
    VIEWER = "viewer"


class AutonomyMode(StrEnum):
    OFF = "off"
    SHADOW = "shadow"
    ASSISTED = "assisted"
    AUTONOMOUS = "autonomous"


class RiskLevel(StrEnum):
    READ = "read"
    WRITE_LOW = "write_low"
    WRITE_HIGH = "write_high"


ROLE_PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.OWNER: frozenset({"*"}),
    Role.MANAGER: frozenset(
        {"read", "manage_catalog", "manage_orders", "manage_approvals", "manage_api_keys"}
    ),
    Role.AGENT_OPERATOR: frozenset({"read", "run_agents", "manage_approvals"}),
    Role.VIEWER: frozenset({"read"}),
}


def role_allows(role: Role, permission: str) -> bool:
    """Return whether a role grants one permission."""
    permissions = ROLE_PERMISSIONS[role]
    return "*" in permissions or permission in permissions


def may_execute_write(mode: AutonomyMode, risk: RiskLevel, in_rule: bool) -> bool:
    """Apply the tenant autonomy policy to a proposed write."""
    if mode in (AutonomyMode.OFF, AutonomyMode.SHADOW):
        return False
    if mode == AutonomyMode.ASSISTED:
        return False
    return risk == RiskLevel.WRITE_LOW and in_rule

