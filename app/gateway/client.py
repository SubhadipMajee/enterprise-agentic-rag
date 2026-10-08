import logfire
from portkey_ai import Portkey, createHeaders, PORTKEY_GATEWAY_URL
from langchain_openai import ChatOpenAI

from app.config import settings


# Production gateway config:
#   - Fallback: primary @rag/llama-3.3-70b-versatile → @brag/llama-3.1-8b-instant on failure
#   - Cache: semantic mode (requires Portkey Enterprise — silently falls back to simple on free/starter)
#   - Retry: 2 attempts on rate limit / server error before triggering the fallback target
GATEWAY_CONFIG = {
    "strategy": {"mode": "fallback"},
    "cache": {"mode": "simple"},
    "retry": {
        "attempts": 2,
        "on_status_codes": [429, 503]
    },
    "targets": [
        {"override_params": {"model": f"@{settings.GROQ_SLUG}/llama-3.3-70b-versatile"}},
        {"override_params": {"model": f"@{settings.GROQ_SLUG_2}/llama-3.1-8b-instant"}},
    ]
}

portkey_client = Portkey(
    api_key=settings.PORTKEY_API_KEY,
    config=GATEWAY_CONFIG
)


from langchain_groq import ChatGroq


class FallbackChatModel:
    """Invokes primary LLM (Portkey) and automatically falls back to direct ChatGroq on failure."""

    def __init__(self, primary, fallback):
        self.primary = primary
        self.fallback = fallback

    def invoke(self, *args, **kwargs):
        if not self.primary:
            return self.fallback.invoke(*args, **kwargs)
        try:
            return self.primary.invoke(*args, **kwargs)
        except Exception as e:
            logfire.warning(f"Primary LLM invocation failed ({e}). Falling back to direct ChatGroq.")
            return self.fallback.invoke(*args, **kwargs)

    def __getattr__(self, name):
        if self.primary and hasattr(self.primary, name):
            return getattr(self.primary, name)
        return getattr(self.fallback, name)


def get_langchain_llm(feature: str = "rag"):
    """
    Returns an optimized ChatGroq instance using Groq's high-speed inference engine.
    If Portkey routing is configured, wraps with automatic fallback to ChatGroq on error.
    """
    groq_llm = ChatGroq(
        api_key=settings.GROQ_API_KEY or "not_configured",
        model_name=settings.GROQ_MODEL,
        temperature=0,
    )

    if settings.PORTKEY_API_KEY:
        try:
            portkey_llm = ChatOpenAI(
                api_key=settings.PORTKEY_API_KEY,
                base_url=PORTKEY_GATEWAY_URL,
                model=f"@{settings.GROQ_SLUG}/{settings.GROQ_MODEL}",
                temperature=0,
                default_headers=createHeaders(
                    api_key=settings.PORTKEY_API_KEY,
                    metadata={
                        "feature": feature,
                        "_user": "rag-system",
                        "environment": settings.APP_ENV,
                    }
                )
            )
            return FallbackChatModel(primary=portkey_llm, fallback=groq_llm)
        except Exception as e:
            logfire.warning(f"Portkey initialization skipped ({e}), using direct ChatGroq.")

    return groq_llm

def extract_cache_status(response) -> str:
    """
    Pull x-portkey-cache-status from the Portkey native client response headers.
    Tries multiple attribute paths defensively — returns 'MISS' if not found.
    """
    for attr in ("_raw_response", "_response", "_http_response"):
        raw = getattr(response, attr, None)
        if raw is not None:
            status = getattr(raw, "headers", {}).get("x-portkey-cache-status", "")
            if status:
                return status.upper()
    return "MISS"