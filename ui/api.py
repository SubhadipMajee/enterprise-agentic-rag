import os
import requests
from pathlib import Path


def _secret(name: str, default: str = "") -> str:
    try:
        import streamlit as st
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return os.getenv(name, default)


def backend_url() -> str:
    return _secret("BACKEND_URL", "http://localhost:8000").rstrip("/")


def api_headers(user_id: str, debug: bool = False) -> dict:
    headers = {
        "Content-Type": "application/json",
        "X-User-Id": user_id,
    }
    api_key = _secret("API_KEY")
    if api_key:
        headers["X-API-Key"] = api_key
    debug_key = _secret("DEBUG_KEY")
    if debug and debug_key:
        headers["X-Debug-Key"] = debug_key
    return headers


def post_query(question: str, user_id: str, timeout: int = 90, debug: bool = False) -> dict:
    url = f"{backend_url()}/query"
    response = requests.post(
        url,
        json={"q": question},
        headers=api_headers(user_id, debug=debug),
        timeout=timeout,
    )
    if response.status_code == 401:
        raise RuntimeError("Authentication failed. Check API_KEY.")
    if response.status_code == 429:
        raise RuntimeError("Too many requests. Please wait a moment and try again.")
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text
        raise RuntimeError(f"The assistant is unavailable ({response.status_code}): {detail}")
    return response.json()


def post_ingest(files: list, user_id: str, timeout: int = 300) -> dict:
    multipart_files = [("files", (file.name, file.getvalue(), file.type or "application/octet-stream")) for file in files]
    headers = api_headers(user_id)
    headers.pop("Content-Type", None)
    response = requests.post(f"{backend_url()}/ingest", files=multipart_files, headers=headers, timeout=timeout)
    if response.status_code == 401:
        raise RuntimeError("Authentication failed. Check API_KEY.")
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text
        raise RuntimeError(f"The import failed ({response.status_code}): {detail}")
    return response.json()


def load_legal(name: str) -> str:
    path = Path(__file__).resolve().parents[1] / "legal" / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    return f"{name} is not available."
