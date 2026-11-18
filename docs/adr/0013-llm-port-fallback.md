# 0013. LLM provider port with fallback

- Status: accepted
- Date: 2026-11-18

## Context

Agent models may need to change by tenant, region, capability, or availability.

## Decision drivers

Provider portability, fallback behavior, PII controls, latency, and per-tenant cost limits.

## Options considered

- Provider-neutral LLMPort with primary and fallback model adapters.
- Direct vendor SDK calls throughout agent implementations.

## Evidence

The owner requirements now identify the Gemini free tier and ask for a fallback when one key fails.
Google's official SDK documents `google-genai`, asynchronous generation, and output-token controls
([SDK documentation](https://googleapis.github.io/python-genai/)); the current Gemini pricing page
lists `gemini-3.8-flash` under the free tier ([pricing](https://ai.google.dev/gemini-api/docs/pricing)).
No live request, provider latency, or quality benchmark has been measured.

## Decision

Use a provider-neutral `LLMPort`, provider-call adapter, configurable fallback wrapper, and
deterministic synthetic fake for tests. The first provider adapter uses Gemini Developer API with a
primary environment key and ordered fallback keys. The model is configurable; default to
`gemini-3.8-flash` with a `gemini-3.6-flash` fallback until the owner changes either model.

## Consequences

Keys are read only from environment variables or a secret manager. Gemini free-tier requests may be
used to improve Google products; minimize direct identifiers before sending and do not send
customer-confidential data until the privacy review and stronger PII controls are complete. Provider
region, fallback project ownership, rate limits, and real-model benchmarks remain open.

