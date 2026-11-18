"""Choose a local synthetic LLM or configured Gemini key pool."""

from clos.adapters.llm.gemini import build_gemini_llm
from clos.adapters.llm.providers import FakeLLM, FallbackLLM
from clos.application.llm import LLMPort
from clos.config import Settings


def build_worker_llm(settings: Settings) -> LLMPort:
    primary = (
        settings.gemini_api_key.get_secret_value() if settings.gemini_api_key is not None else ""
    )
    fallbacks = (
        settings.gemini_fallback_api_keys.get_secret_value().split(",")
        if settings.gemini_fallback_api_keys is not None
        else []
    )
    keys = [primary, *fallbacks]
    if any(key.strip() for key in keys):
        return FallbackLLM(
            primary=build_gemini_llm(keys, settings.gemini_model),
            fallback=build_gemini_llm(keys, settings.gemini_fallback_model),
        )
    if settings.app_env in {"local", "test", "development"}:
        return FakeLLM()
    raise RuntimeError("GEMINI_API_KEY is required outside local and test environments")
