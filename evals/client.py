import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/") + "/query"


def query_headers(user_id: str = "eval-runner") -> dict:
    headers = {
        "Content-Type": "application/json",
        "X-User-Id": user_id,
    }
    api_key = os.getenv("API_KEY", "")
    if api_key:
        headers["X-API-Key"] = api_key
    debug_key = os.getenv("DEBUG_KEY", "")
    if debug_key:
        headers["X-Debug-Key"] = debug_key
    return headers


def post_eval_query(payload: dict, timeout: int) -> requests.Response:
    return requests.post(API_URL, json=payload, headers=query_headers(), timeout=timeout)
