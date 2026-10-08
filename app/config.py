import os
from dotenv import load_dotenv

load_dotenv()


def _clean_str(name: str, default: str = "") -> str:
    raw = os.getenv(name)
    if raw is None:
        return default
    val = raw.strip()
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        val = val[1:-1].strip()
    return val


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return int(raw)


def _csv(name: str) -> list[str]:
    return [part.strip() for part in os.getenv(name, "").split(",") if part.strip()]


class Settings:
    APP_ENV = _clean_str("APP_ENV", "development").lower()

    ASSISTANT_NAME = _clean_str("ASSISTANT_NAME", "Enterprise Assistant")
    ASSISTANT_SCOPE = _clean_str(
        "ASSISTANT_SCOPE",
        "your organization's approved documentation",
    )

    GEMINI_API_KEY = _clean_str("GEMINI_API_KEY") or _clean_str("GOOGLE_API_KEY")

    QDRANT_URL = _clean_str("QDRANT_CLUSTER_ENDPOINT") or _clean_str("QDRANT_URL")
    QDRANT_API_KEY = _clean_str("QDRANT_API_KEY")
    QDRANT_COLLECTION = _clean_str("QDRANT_COLLECTION", "enterprise_rag")

    GROQ_API_KEY = _clean_str("GROQ_API_KEY")
    GROQ_MODEL = _clean_str("GROQ_MODEL", "openai/gpt-oss-120b")
    GROQ_FALLBACK_API_KEY = _clean_str("GROQ_FALLBACK_API_KEY")

    PORTKEY_API_KEY = _clean_str("PORTKEY_API_KEY")
    GROQ_SLUG = _clean_str("GROQ_SLUG", "rag")
    GROQ_SLUG_2 = _clean_str("GROQ_SLUG_2", "brag")

    API_KEY = _clean_str("API_KEY", "")
    DEBUG_KEY = _clean_str("DEBUG_KEY", "")
    APP_PASSWORD = _clean_str("APP_PASSWORD", "")
    CORS_ORIGINS = _csv("CORS_ORIGINS")

    MAX_QUERY_LENGTH = _int("MAX_QUERY_LENGTH", 2000)
    MAX_UPLOAD_SIZE_MB = _int("MAX_UPLOAD_SIZE_MB", 25)
    RATE_LIMIT_REQUESTS = _int("RATE_LIMIT_REQUESTS", 30)
    RATE_LIMIT_WINDOW_SECONDS = _int("RATE_LIMIT_WINDOW_SECONDS", 60)

    DATABASE_URL = _clean_str("DATABASE_URL", "")
    REDIS_URL = _clean_str("REDIS_URL", "")

    # Auto-detect checkpoint backend if not explicitly set
    _backend_env = _clean_str("CHECKPOINT_BACKEND").lower()
    if _backend_env:
        CHECKPOINT_BACKEND = _backend_env
    elif DATABASE_URL:
        CHECKPOINT_BACKEND = "postgres"
    elif REDIS_URL:
        CHECKPOINT_BACKEND = "redis"
    else:
        CHECKPOINT_BACKEND = "memory"

    BACKEND_URL = _clean_str("BACKEND_URL", "http://localhost:8000")
    SHOW_INTERNAL_DETAILS = _bool("SHOW_INTERNAL_DETAILS", False)
    LOG_USER_CONTENT = _bool("LOG_USER_CONTENT", APP_ENV != "production")

    LANGSMITH_TRACING = _clean_str(
        "LANGSMITH_TRACING",
        "false" if APP_ENV == "production" else "true",
    )
    LANGSMITH_API_KEY = _clean_str("LANGSMITH_API_KEY")
    LANGSMITH_PROJECT = _clean_str("LANGSMITH_PROJECT", "rag_scale_test")
    LANGSMITH_ENDPOINT = _clean_str(
        "LANGSMITH_ENDPOINT",
        "https://api.smith.langchain.com",
    )

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    def validate(self) -> None:
        missing = []
        required = [
            ("GROQ_API_KEY", self.GROQ_API_KEY),
            ("PORTKEY_API_KEY", self.PORTKEY_API_KEY),
            ("QDRANT_API_KEY", self.QDRANT_API_KEY),
            ("QDRANT_CLUSTER_ENDPOINT (or QDRANT_URL)", self.QDRANT_URL),
            ("GEMINI_API_KEY (or GOOGLE_API_KEY)", self.GEMINI_API_KEY),
        ]
        if self.is_production:
            if not self.API_KEY:
                missing.append("API_KEY")
            if not self.APP_PASSWORD:
                missing.append("APP_PASSWORD")

        for name, value in required:
            if not value:
                missing.append(name)

        if missing:
            import sys
            msg = (
                f"\n{'='*70}\n"
                f"MISSING REQUIRED ENVIRONMENT VARIABLES:\n"
                f"  - " + "\n  - ".join(missing) + "\n"
                f"Please add them under Render Dashboard -> Environment Variables.\n"
                f"{'='*70}\n"
            )
            sys.stderr.write(msg)
            sys.stderr.flush()
            raise RuntimeError(
                "Missing required environment variables: " + ", ".join(missing)
            )

        if self.is_production and self.CHECKPOINT_BACKEND == "memory":
            import logfire
            logfire.warning(
                "CHECKPOINT_BACKEND is 'memory' in production. "
                "Conversation state will not persist across service restarts or spin-downs. "
                "Set DATABASE_URL (for Postgres) or REDIS_URL to enable durable persistence."
            )

        if self.CHECKPOINT_BACKEND == "redis" and not self.REDIS_URL:
            raise RuntimeError("REDIS_URL is required when CHECKPOINT_BACKEND=redis.")
        if self.CHECKPOINT_BACKEND == "postgres" and not self.DATABASE_URL:
            raise RuntimeError(
                "DATABASE_URL is required when CHECKPOINT_BACKEND=postgres."
            )


settings = Settings()

os.environ["LANGCHAIN_TRACING_V2"] = settings.LANGSMITH_TRACING
os.environ["LANGCHAIN_API_KEY"] = settings.LANGSMITH_API_KEY or ""
os.environ["LANGCHAIN_PROJECT"] = settings.LANGSMITH_PROJECT
os.environ["LANGCHAIN_ENDPOINT"] = settings.LANGSMITH_ENDPOINT
