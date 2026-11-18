# Gemini provider configuration

The worker uses the official Google Gen AI Python SDK through the application `LLMPort`.

## Configure keys

- Set `GEMINI_API_KEY` in the process environment or a secret manager.
- Optionally set `GEMINI_FALLBACK_API_KEYS` to a comma-separated list of additional keys. The
  worker tries them in order when a request fails. Prefer keys from separate projects so a quota
  failure is less likely to affect every key.
- `GEMINI_MODEL` defaults to `gemini-3.8-flash`; if all configured keys fail for it, the worker
  retries with `GEMINI_FALLBACK_MODEL` (`gemini-3.6-flash` by default). Set both to models enabled
  for the configured account.
- Never put real keys in `.env.example`, source control, logs, prompts, or test fixtures.

Tests use `FakeLLM` and make no Gemini requests. No live provider request has been made in this
phase. Gemini free-tier prompts may be used to improve provider products. The adapter redacts email,
phone-number, and credential-shaped strings, but it is not a complete PII detector. Avoid customer
names, addresses, order details, or other confidential data until privacy controls are reviewed.

If every configured key fails, the run raises a provider error and the Celery task uses its normal
retry policy. It does not silently return a synthetic response.
