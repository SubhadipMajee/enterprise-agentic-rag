"""Shared Streamlit chat UI for local and hosted deployments."""
import hmac
import sys
import time
import uuid
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from ui.api import _secret, load_legal, post_ingest, post_query

ASSISTANT_NAME = _secret("ASSISTANT_NAME", "Enterprise Assistant")
SHOW_INTERNAL = _secret("SHOW_INTERNAL_DETAILS", "false").lower() in ("1", "true", "yes")


def _require_login() -> bool:
    if "authed" not in st.session_state:
        st.session_state.authed = False

    password = _secret("APP_PASSWORD")
    if not password:
        if not st.session_state.authed:
            st.session_state.authed = True
            st.session_state.user_base = "dev-local"
            st.session_state.user_id = "dev-local"
        return True

    if st.session_state.authed:
        return True

    st.title(ASSISTANT_NAME)
    st.caption("Sign in to continue.")
    with st.form("login"):
        username = st.text_input("Username or email")
        entered = st.text_input("Access password", type="password")
        submitted = st.form_submit_button("Sign in")
    if submitted:
        clean = "".join(ch for ch in username.strip() if ch.isalnum() or ch in "._@-")[:64]
        if hmac.compare_digest(entered, password) and clean:
            st.session_state.authed = True
            st.session_state.user_base = clean
            st.session_state.user_id = clean
            st.rerun()
        st.error("Invalid username or password.")
    with st.expander("Privacy"):
        st.markdown(load_legal("PRIVACY.md"))
    with st.expander("Terms of use"):
        st.markdown(load_legal("TERMS.md"))
    return False


def render_app():
    st.set_page_config(page_title=ASSISTANT_NAME, page_icon="💬", layout="wide")

    if not _require_login():
        return

    if "messages" not in st.session_state:
        st.session_state.messages = []

    user_id = st.session_state.get("user_id") or "dev-local"

    with st.sidebar:
        st.title(ASSISTANT_NAME)
        st.caption("Answers come from your indexed documentation.")
        with st.expander("Import data", expanded=True):
            st.caption("Add PDF, HTML, TXT, DOCX, or PPTX files to the knowledge base.")
            uploaded_files = st.file_uploader(
                "Choose documents",
                type=["pdf", "html", "htm", "txt", "docx", "pptx"],
                accept_multiple_files=True,
                key="knowledge_uploads",
            )
            if st.button("Import selected files", width="stretch", disabled=not uploaded_files):
                with st.spinner("Parsing and indexing documents..."):
                    try:
                        result = post_ingest(uploaded_files, user_id)
                        imported = result.get("imported", 0)
                        st.success(f"Imported {imported} of {result.get('total', 0)} file(s)." if imported else "No files were imported.")
                        for item in result.get("results", []):
                            if item.get("status") != "imported":
                                st.warning(f"{item.get('filename')}: {item.get('detail')}")
                    except Exception as exc:
                        st.error(str(exc))
        if st.button("New conversation", width="stretch"):
            st.session_state.messages = []
            base = st.session_state.get("user_base") or user_id
            st.session_state.user_id = f"{base}-{uuid.uuid4().hex[:6]}"
            st.rerun()
        if _secret("APP_PASSWORD") and st.button("Sign out", width="stretch"):
            st.session_state.authed = False
            st.session_state.messages = []
            st.rerun()
        st.markdown("---")
        with st.expander("Privacy"):
            st.markdown(load_legal("PRIVACY.md"))
        with st.expander("Terms of use"):
            st.markdown(load_legal("TERMS.md"))

    st.title(ASSISTANT_NAME)
    st.caption("Ask a question about your documentation.")

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Ask about your documentation..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            placeholder = st.empty()
            try:
                data = post_query(prompt, user_id, debug=SHOW_INTERNAL)
            except Exception:
                placeholder.error(
                    "The assistant is temporarily unavailable. Please try again in a moment."
                )
                st.stop()

            if SHOW_INTERNAL:
                steps = data.get("thought_process") or []
                for step in steps:
                    st.caption(str(step))

            full_answer = data.get("answer") or "No response."
            curr_text = ""
            for char in full_answer:
                curr_text += char
                placeholder.markdown(curr_text + "▌")
                time.sleep(0.004)
            placeholder.markdown(full_answer)

            if SHOW_INTERNAL:
                sources = data.get("sources") or []
                if sources:
                    with st.expander(f"Retrieved context ({len(sources)} chunks)"):
                        for i, source in enumerate(sources):
                            st.caption(f"Chunk {i + 1}")
                            st.info(source)

            st.session_state.messages.append({"role": "assistant", "content": full_answer})
