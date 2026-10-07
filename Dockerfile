# =============================================================================
# Multi-stage build for Enterprise Agentic RAG
# Stage 1: Install dependencies (cached layer)
# Stage 2: Copy app code + run (smaller final image)
# =============================================================================

# ── Stage 1: Builder ─────────────────────────────────────────────────────────
FROM python:3.11-slim-bookworm AS builder

RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    gcc g++ libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements-prod.txt .
RUN pip install --no-cache-dir --prefer-binary -r requirements-prod.txt


# ── Stage 2: Runtime ─────────────────────────────────────────────────────────
FROM python:3.11-slim-bookworm AS runtime

# Install only runtime system deps (no compiler toolchain)
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

WORKDIR /app

# Copy only the app package — everything else (evals/, ui/, DATA/, DOCS/) stays out
COPY app/ ./app/

# Run as non-root user for security
RUN useradd --create-home --no-log-init appuser
RUN mkdir -p /app/processed_data && chown -R appuser:appuser /app
USER appuser

ENV APP_ENV=production
ENV PORT=8080

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8080}/health || exit 1

EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
