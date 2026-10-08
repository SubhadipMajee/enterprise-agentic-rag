# ============================================================
# CRITICAL: logfire MUST be configured before ALL other imports
# so that spans from all modules are captured from the start.
# ============================================================
import logfire
import os
import tempfile
from pathlib import Path
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()
_logfire_token = os.getenv("LOGFIRE_TOKEN")
if _logfire_token and _logfire_token.strip():
    logfire.configure(token=_logfire_token.strip())
else:
    logfire.configure(send_to_logfire=False)

from fastapi import Depends, FastAPI, File, HTTPException, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from typing import Optional

from app.config import settings
from app.agents.graph import compile_agent, get_agent
from app.guardrails import initialize_rails, guard
from app.ingestion.processor import process_file
from app.security import authenticate

SUPPORTED_UPLOAD_TYPES = {".pdf", ".html", ".htm", ".txt", ".docx", ".pptx"}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    import sys
    import traceback
    try:
        settings.validate()

        # ── CORS safety checks ──
        if settings.is_production:
            if not settings.CORS_ORIGINS:
                logfire.warning(
                    "CORS_ORIGINS is empty. Browser apps cannot call the API; "
                    "server-side Streamlit still works."
                )
            if "*" in settings.CORS_ORIGINS:
                logfire.warning(
                    "CORS_ORIGINS contains '*' — wildcard origins are not recommended in production."
                )

        initialize_rails()
        compile_agent()
        logfire.info("Backend service initialized successfully.")
        print(f"Backend service initialized successfully. Environment: {settings.APP_ENV}", flush=True)
        yield
    except Exception as exc:
        msg = f"\n{'='*70}\nCRITICAL STARTUP FAILURE IN LIFESPAN:\n{exc}\n{'='*70}\n"
        sys.stderr.write(msg)
        sys.stdout.write(msg)
        traceback.print_exc(file=sys.stderr)
        traceback.print_exc(file=sys.stdout)
        sys.stderr.flush()
        sys.stdout.flush()
        raise exc


app = FastAPI(
    title=f"{settings.ASSISTANT_NAME} API",
    lifespan=lifespan,
)

if settings.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "X-API-Key", "X-User-Id", "X-Debug-Key", "Content-Type"],
    )


class QueryRequest(BaseModel):
    q: str = Field(..., min_length=1)
    thread_id: Optional[str] = Field(
        default=None,
        description="Ignored. Conversation identity comes from X-User-Id.",
    )


def _preview(text: str) -> str:
    if settings.LOG_USER_CONTENT:
        return text[:80]
    return f"<{len(text)} chars>"


@app.get("/")
def home():
    return {"message": f"{settings.ASSISTANT_NAME} API is live.", "env": settings.APP_ENV}


@app.get("/health")
def health():
    agent_ready = get_agent() is not None
    return {
        "status": "ok" if agent_ready else "starting",
        "env": settings.APP_ENV,
        "checkpoint": settings.CHECKPOINT_BACKEND,
        "collection": settings.QDRANT_COLLECTION,
    }


@app.get("/graph")
def get_graph_image(identity: dict = Depends(authenticate)):
    try:
        png_bytes = get_agent().get_graph().draw_mermaid_png()
        return Response(content=png_bytes, media_type="image/png")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not generate graph image: {e}",
        )


@app.post("/query")
def query(request: QueryRequest, identity: dict = Depends(authenticate)):
    q = request.q.strip()
    if len(q) > settings.MAX_QUERY_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Query exceeds max length of {settings.MAX_QUERY_LENGTH} characters.",
        )

    thread_id = identity["thread_id"]
    include_internal = identity["include_internal"]

    initial_state = {
        "messages": [{"role": "user", "content": q}],
        "current_query": q,
        "documents": [],
        "plan": ["Start"],
        "status": "Initializing Graph...",
    }
    config = {"configurable": {"thread_id": thread_id}}

    try:
        rail_fired, rail_response = guard(q)
        if rail_fired:
            logfire.info(f"Request blocked by guardrails | thread={thread_id}")
            payload = {
                "question": q if settings.LOG_USER_CONTENT else None,
                "answer": rail_response,
                "status": "Blocked by guardrails.",
                "blocked": True,
            }
            if include_internal:
                payload["thought_process"] = ["Intent: Guardrails Fired", "Retrieval: Skipped"]
                payload["sources"] = []
            return payload

        final_output = get_agent().invoke(initial_state, config=config)
        payload = {
            "question": q if settings.LOG_USER_CONTENT else None,
            "answer": final_output.get("final_answer"),
            "status": final_output.get("status"),
            "blocked": False,
        }
        if include_internal:
            payload["thought_process"] = final_output.get("plan")
            payload["sources"] = final_output.get("documents", [])
        return payload
    except HTTPException:
        raise
    except Exception as e:
        import sys
        import traceback
        sys.stderr.write(f"\n[BACKEND ERROR] Execution failed for query '{_preview(q)}': {e}\n")
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        logfire.error(f"Backend execution failed: {e} | preview={_preview(q)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backend execution error: {e}",
        )


@app.post("/ingest")
async def ingest(files: list[UploadFile] = File(...), identity: dict = Depends(authenticate)):
    if not files:
        raise HTTPException(status_code=400, detail="Select at least one file to import.")
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    results = []
    for upload in files:
        filename = Path(upload.filename or "").name
        suffix = Path(filename).suffix.lower()
        if not filename or suffix not in SUPPORTED_UPLOAD_TYPES:
            results.append({"filename": filename or "unnamed file", "status": "rejected", "detail": "Supported types: PDF, HTML, TXT, DOCX, PPTX."})
            continue
        contents = await upload.read()
        if len(contents) > max_bytes:
            results.append({"filename": filename, "status": "rejected", "detail": f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB limit."})
            continue
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_file.write(contents)
                temp_path = temp_file.name
            processed = await run_in_threadpool(process_file, temp_path, filename, "user_uploads")
            results.append({"filename": filename, "status": "imported" if processed else "failed", "detail": "Indexed successfully." if processed else "No readable text was found or indexing failed."})
        except Exception as exc:
            logfire.error(f"Upload processing failed for {filename}: {exc}")
            results.append({"filename": filename, "status": "failed", "detail": "Document processing or indexing failed. Check the backend log for details."})
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
    return {"imported": sum(item["status"] == "imported" for item in results), "total": len(results), "results": results}
