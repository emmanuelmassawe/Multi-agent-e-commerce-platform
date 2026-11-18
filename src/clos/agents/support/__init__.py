"""Customer support drafting with mandatory tenant and customer scoped retrieval."""

from clos.agents.common import AgentContext, RetrievedDocument, SupportRetrievalPort


class SupportAgent:
    def __init__(self, retrieval: SupportRetrievalPort) -> None:
        self.retrieval = retrieval

    async def answer_customer(self, query: str, context: AgentContext) -> dict[str, object]:
        if context.customer_id is None:
            raise ValueError("Customer-scoped support requires a customer ID")
        docs = await self.retrieval.search(context.tenant_id, context.customer_id, query, limit=5)
        snippets = [
            {"document_id": str(doc.document_id), "source": doc.source, "text": doc.text}
            for doc in docs
        ]
        return {"answer": self._draft(query, docs), "evidence": snippets, "sent": False}

    def generate_report(
        self, *, daily_sales: str, shipments: str, inventory: str
    ) -> dict[str, str]:
        return {"daily_sales": daily_sales, "shipments": shipments, "inventory": inventory}

    def escalate_to_human(self, reason: str, context: AgentContext) -> dict[str, object]:
        return {
            "tenant_id": str(context.tenant_id),
            "customer_id": str(context.customer_id) if context.customer_id else None,
            "reason": reason,
            "status": "draft_escalation",
        }

    @staticmethod
    def _draft(query: str, docs: list[RetrievedDocument]) -> str:
        if not docs:
            return (
                "I could not find an approved answer in the available information. "
                "I can refer this to a person."
            )
        excerpts = " ".join(doc.text.strip() for doc in docs if doc.text.strip())
        return (
            f"Based on the available information: {excerpts}"
            if excerpts
            else f"I received your question: {query}"
        )


__all__ = ["SupportAgent"]
