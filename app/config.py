import os
from dotenv import load_dotenv

load_dotenv()


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
    APP_ENV = os.getenv("APP_ENV", "development").strip().lower()

    ASSISTANT_NAME = os.getenv("ASSISTANT_NAME", "Enterprise Assistant")
    ASSISTANT_SCOPE = os.getenv(
        "ASSISTANT_SCOPE",
        "your organization's approved documentation",
    )

    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

    QDRANT_URL = os.getenv("QDRANT_CLUSTER_ENDPOINT")
    QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
    QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "enterprise_rag")

    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    GROQ_FALLBACK_API_KEY = os.getenv("GROQ_FALLBACK_API_KEY")

    PORTKEY_API_KEY = os.getenv("PORTKEY_API_KEY")
    GROQ_SLUG = os.getenv("GROQ_SLUG", "rag")
    GROQ_SLUG_2 = os.getenv("GROQ_SLUG_2", "brag")

    API_KEY = os.getenv("API_KEY", "")
    DEBUG_KEY = os.getenv("DEBUG_KEY", "")
    APP_PASSWORD = os.getenv("APP_PASSWORD", "")
    CORS_ORIGINS = _csv("CORS_ORIGINS")

    MAX_QUERY_LENGTH = _int("MAX_QUERY_LENGTH", 2000)
    MAX_UPLOAD_SIZE_MB = _int("MAX_UPLOAD_SIZE_MB", 25)
    RATE_LIMIT_REQUESTS = _int("RATE_LIMIT_REQUESTS", 30)
    RATE_LIMIT_WINDOW_SECONDS = _int("RATE_LIMIT_WINDOW_SECONDS", 60)

    CHECKPOINT_BACKEND = os.getenv("CHECKPOINT_BACKEND", "memory").strip().lower()
    DATABASE_URL = os.getenv("DATABASE_URL", "")
    REDIS_URL = os.getenv("REDIS_URL", "")

    BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
    SHOW_INTERNAL_DETAILS = _bool("SHOW_INTERNAL_DETAILS", False)
    LOG_USER_CONTENT = _bool("LOG_USER_CONTENT", APP_ENV != "production")

    LANGSMITH_TRACING = os.getenv(
        "LANGSMITH_TRACING",
        "false" if APP_ENV == "production" else "true",
    )
    LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")
    LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT", "rag_scale_test")
    LANGSMITH_ENDPOINT = os.getenv(
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
            ("QDRANT_CLUSTER_ENDPOINT", self.QDRANT_URL),
            ("GEMINI_API_KEY", self.GEMINI_API_KEY),
        ]
        if self.is_production:
            required.extend(
                [
                    ("API_KEY", self.API_KEY),
                    ("APP_PASSWORD", self.APP_PASSWORD),
                ]
            )
        for name, value in required:
            if not value:
                missing.append(name)

        if missing:
            raise RuntimeError(
                "Missing required environment variables: " + ", ".join(missing)
            )

        if self.is_production and self.CHECKPOINT_BACKEND == "memory":
            raise RuntimeError(
                "CHECKPOINT_BACKEND=memory is not allowed in production. "
                "Set CHECKPOINT_BACKEND=redis (REDIS_URL) or postgres (DATABASE_URL)."
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
