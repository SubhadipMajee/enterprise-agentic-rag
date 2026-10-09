import logfire
from nemoguardrails import RailsConfig, LLMRails

from app.config import settings
from app.guardrails.colang_rules import COLANG_CONTENT, YAML_CONTENT, RAIL_INDICATORS
from app.gateway import get_langchain_llm


_rails: LLMRails | None = None


def initialize_rails() -> None:
    """
    Build the NeMo LLMRails singleton at app startup.
    Uses the configured Portkey gateway for intent classification at the gate,
    so guardrails follow the same routing and fallback configuration as the
    planner and responder.
    """
    global _rails

    guard_llm = get_langchain_llm(feature="guardrails")

    config = RailsConfig.from_content(
        colang_content=COLANG_CONTENT,
        yaml_content=YAML_CONTENT
    )

    _rails = LLMRails(config, llm=guard_llm)
    logfire.info("NeMo Guardrails initialised through Portkey.")
    
    


def guard(message: str) -> tuple[bool, str | None]:
    """
    Run a user message through the NeMo rails gate.

    Returns:
        (True,  rail_response) — a rail fired; return this response immediately,
                                skip the RAG pipeline entirely.
        (False, None)          — message is clean; proceed to LangGraph.
    """
    if _rails is None:
        logfire.warning("⚠️ Guardrails not initialised — skipping gate.")
        return False, None

    with logfire.span("🛡️ Guardrails Check"):
        try:
            result = _rails.generate(messages=[{"role": "user", "content": message}])

            # NeMo returns {'role': 'assistant', 'content': '...'} — extract text
            content = result.get("content", "") if isinstance(result, dict) else str(result)

            fired = any(indicator in content for indicator in RAIL_INDICATORS)

            if fired:
                preview = message[:80] if settings.LOG_USER_CONTENT else f"<{len(message)} chars>"
                logfire.info(f"Guardrails fired | query={preview!r}")
                return True, content

            logfire.info("Guardrails passed.")
            return False, None
        except Exception as e:
            logfire.warning(f"Guardrails check encountered error ({e}) — passing through to LangGraph.")
            return False, None
