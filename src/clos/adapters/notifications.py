"""Approval notification ports and deterministic channel fakes."""

from dataclasses import dataclass

from clos.application.approvals import ApprovalItem, ApprovalNotificationPort


@dataclass(frozen=True, slots=True)
class NotificationRecord:
    channel: str
    event_type: str
    tenant_id: str
    approval_id: str
    payload: dict[str, object]


class FakeChannelNotifier(ApprovalNotificationPort):
    """Test fake; never contacts email or WhatsApp providers."""

    def __init__(self, channel: str) -> None:
        if channel not in {"email", "whatsapp", "dashboard"}:
            raise ValueError("Unsupported approval notification channel")
        self.channel = channel
        self.records: list[NotificationRecord] = []

    async def publish(self, event_type: str, item: ApprovalItem) -> None:
        self.records.append(
            NotificationRecord(
                channel=self.channel,
                event_type=event_type,
                tenant_id=str(item.tenant_id),
                approval_id=str(item.approval_id),
                payload={
                    "action": item.action,
                    "status": item.status,
                    "expires_at": item.expires_at.isoformat(),
                },
            )
        )


class AuditStreamNotifier(ApprovalNotificationPort):
    """Approval events are already committed to audit_logs for dashboard SSE polling."""

    async def publish(self, _event_type: str, _item: ApprovalItem) -> None:
        return None


class CompositeApprovalNotifier(ApprovalNotificationPort):
    def __init__(self, *notifiers: ApprovalNotificationPort) -> None:
        self._notifiers = notifiers

    async def publish(self, event_type: str, item: ApprovalItem) -> None:
        for notifier in self._notifiers:
            await notifier.publish(event_type, item)
