# Business rules (copy this file to main.md and fill in)

Use concrete numbers. Codex will turn these into configurable policies, not hard-coded values.

## Pricing
- Minimum margin per category: 
- Maximum price change per day (% or amount):
- Price change that needs human approval (above X%):
- Competitors to track and how to match (match / undercut by X% / never go below cost+Y):
- Products that must never be repriced automatically:

## Inventory
- Low-stock threshold per category (days of cover or units):
- Reorder: preferred suppliers, minimum order quantities, lead times:
- Reorder amount that needs human approval (above X):

## Logistics
- Carriers allowed per region and service level:
- Delay definition (hours/days past promised date):
- Rebooking cost increase that needs approval (above X):
- Customer notification rules when a shipment is delayed:

## Customer support
- Languages and tone:
- Refund / return policy (plain text; Codex will index it for RAG):
- Discounts the agent may offer without approval (max %):
- Topics the agent must refuse or escalate (legal, medical, payments disputes, etc.):
- Business hours and escalation contacts:

## Approvals
| Action | Threshold | Who approves | Notification channel | Expiry |
|---|---|---|---|---|

## Data
- Data retention periods:
- What personal data is collected and why:
