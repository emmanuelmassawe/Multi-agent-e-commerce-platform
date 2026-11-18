"""Domain identity and policy tests."""

from uuid import UUID

from clos.domain.identity import AutonomyMode, Role, RiskLevel, may_execute_write, role_allows
from clos.domain.ids import new_uuid7


def test_new_uuid7_has_version_and_rfc_variant() -> None:
    value = new_uuid7()
    assert isinstance(value, UUID)
    assert value.version == 7
    assert value.variant == "specified in RFC 4122"


def test_role_permissions_are_scoped() -> None:
    assert role_allows(Role.OWNER, "manage_api_keys")
    assert role_allows(Role.MANAGER, "manage_orders")
    assert not role_allows(Role.VIEWER, "manage_orders")


def test_autonomy_never_executes_high_risk_without_approval() -> None:
    assert not may_execute_write(AutonomyMode.SHADOW, RiskLevel.WRITE_LOW, True)
    assert may_execute_write(AutonomyMode.AUTONOMOUS, RiskLevel.WRITE_LOW, True)
    assert not may_execute_write(AutonomyMode.AUTONOMOUS, RiskLevel.WRITE_HIGH, True)
    assert not may_execute_write(AutonomyMode.AUTONOMOUS, RiskLevel.WRITE_LOW, False)

