"""Premium Enterprise Streamlit chat UI for local and hosted deployments."""
import hmac
import re
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

from ui.api import _secret, get_health, load_legal, post_ingest, post_query

ASSISTANT_NAME = _secret("ASSISTANT_NAME", "Enterprise Assistant")
ASSISTANT_SCOPE = _secret("ASSISTANT_SCOPE", "Technical Documentation")
SHOW_INTERNAL = _secret("SHOW_INTERNAL_DETAILS", "true").lower() in ("1", "true", "yes")

CUSTOM_CSS = """
<style>
/* Modern styling for Enterprise RAG */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* Header style */
.hero-container {
    padding: 1.2rem 1.5rem;
    border-radius: 12px;
    background: linear-gradient(135deg, rgba(30, 41, 59, 0.6) 0%, rgba(15, 23, 42, 0.8) 100%);
    border: 1px solid rgba(255, 255, 255, 0.08);
    margin-bottom: 1.5rem;
}

.hero-title {
    font-size: 1.6rem;
    font-weight: 700;
    margin: 0;
    background: linear-gradient(90deg, #60A5FA, #A78BFA);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.hero-subtitle {
    font-size: 0.9rem;
    color: #94A3B8;
    margin-top: 0.3rem;
    margin-bottom: 0;
}

/* Status Badges */
.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 600;
}

.status-online {
    background-color: rgba(16, 185, 129, 0.15);
    color: #10B981;
    border: 1px solid rgba(16, 185, 129, 0.3);
}

.status-offline {
    background-color: rgba(239, 68, 68, 0.15);
    color: #EF4444;
    border: 1px solid rgba(239, 68, 68, 0.3);
}

.tech-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 6px;
    font-size: 0.7rem;
    font-weight: 500;
    background: rgba(255, 255, 255, 0.06);
    color: #CBD5E1;
    margin: 2px;
    border: 1px solid rgba(255, 255, 255, 0.08);
}

/* Prompt Starter Cards */
.starter-card {
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 10px;
    padding: 1rem;
    transition: all 0.2s ease;
    cursor: pointer;
    min-height: 80px;
}

.starter-card:hover {
    background: rgba(99, 102, 241, 0.1);
    border-color: rgba(99, 102, 241, 0.4);
    transform: translateY(-2px);
}

/* Reasoning Block */
.reasoning-box {
    background-color: rgba(30, 41, 59, 0.5);
    border-left: 3px solid #6366F1;
    padding: 10px 14px;
    border-radius: 0 8px 8px 0;
    font-size: 0.85rem;
    color: #94A3B8;
    margin-bottom: 0.8rem;
    font-style: italic;
}

/* Source Card */
.source-box {
    background: rgba(15, 23, 42, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 8px;
    padding: 10px 12px;
    margin-bottom: 8px;
    font-size: 0.82rem;
    color: #CBD5E1;
}
</style>
"""


def _extract_thinking(text: str) -> tuple[str | None, str]:
    """Extract <think>...</think> reasoning blocks cleanly."""
    if not text:
        return None, ""
    match = re.search(r"<think>(.*?)</think>", text, flags=re.DOTALL)
    if match:
        thinking = match.group(1).strip()
        clean = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        return thinking, clean
    return None, text


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

    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="hero-container" style="text-align: center; max-width: 480px; margin: 4rem auto 1.5rem auto;">
            <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">🏢</div>
            <h2 class="hero-title">{ASSISTANT_NAME}</h2>
            <p class="hero-subtitle">Enterprise Agentic RAG Platform</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _, col, _ = st.columns([1, 1.2, 1])
    with col:
        with st.form("login"):
            username = st.text_input("Username / Email", placeholder="e.g. admin or employee@org.com")
            entered = st.text_input("Access Password", type="password", placeholder="Enter authorization key")
            submitted = st.form_submit_button("Sign in to Assistant", use_container_width=True)

        if submitted:
            clean = "".join(ch for ch in username.strip() if ch.isalnum() or ch in "._@-")[:64]
            if hmac.compare_digest(entered, password) and clean:
                st.session_state.authed = True
                st.session_state.user_base = clean
                st.session_state.user_id = clean
                st.rerun()
            st.error("Invalid username or password.")

        with st.expander("Privacy Policy & Terms"):
            st.caption(load_legal("PRIVACY.md"))
            st.caption(load_legal("TERMS.md"))

    return False


def render_app():
    st.set_page_config(
        page_title=f"{ASSISTANT_NAME} | Enterprise RAG",
        page_icon="🧠",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    if not _require_login():
        return

    if "messages" not in st.session_state:
        st.session_state.messages = []

    user_id = st.session_state.get("user_id") or "dev-local"

    # ── Sidebar ──
    with st.sidebar:
        st.markdown(
            f"""
            <div style="padding-bottom: 0.8rem; border-bottom: 1px solid rgba(255,255,255,0.08); margin-bottom: 1rem;">
                <h3 style="margin: 0; font-size: 1.2rem; font-weight: 700; color: #F8FAFC;">{ASSISTANT_NAME}</h3>
                <span style="font-size: 0.78rem; color: #94A3B8;">Scope: {ASSISTANT_SCOPE}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Live Backend Health Indicator
        health = get_health(timeout=3)
        if health.get("status") == "ok":
            st.markdown(
                """
                <div class="status-pill status-online" style="margin-bottom: 1rem;">
                    <span>●</span> API Live (Render Cloud)
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                """
                <div class="status-pill status-offline" style="margin-bottom: 1rem;">
                    <span>●</span> API Offline / Waking Up
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Knowledge Base Upload
        with st.expander("📂 Knowledge Base Ingestion", expanded=False):
            st.caption("Upload company docs to embed into Qdrant Vector Cloud.")
            uploaded_files = st.file_uploader(
                "Select documents",
                type=["pdf", "html", "htm", "txt", "docx", "pptx"],
                accept_multiple_files=True,
                key="knowledge_uploads",
                label_visibility="collapsed",
            )
            if st.button("Index Documents", use_container_width=True, disabled=not uploaded_files):
                with st.spinner("Processing embeddings & chunking..."):
                    try:
                        result = post_ingest(uploaded_files, user_id)
                        imported = result.get("imported", 0)
                        if imported:
                            st.success(f"Successfully indexed {imported} file(s)!")
                        else:
                            st.warning("No new content was indexed.")
                        for item in result.get("results", []):
                            if item.get("status") != "imported":
                                st.error(f"{item.get('filename')}: {item.get('detail')}")
                    except Exception as exc:
                        st.error(f"Ingestion failed: {exc}")

        # System Architecture Telemetry
        with st.expander("⚙️ System Architecture", expanded=True):
            st.markdown(
                f"""
                <div style="font-size: 0.8rem; line-height: 1.6;">
                    <div><b>Reasoning Engine:</b> <span class="tech-badge">Groq Llama 3.3</span></div>
                    <div><b>Orchestrator:</b> <span class="tech-badge">LangGraph Cyclic</span></div>
                    <div><b>Vector DB:</b> <span class="tech-badge">Qdrant Cloud</span></div>
                    <div><b>Reranker:</b> <span class="tech-badge">FlashRank</span></div>
                    <div><b>Checkpointer:</b> <span class="tech-badge">{health.get('checkpoint', 'Postgres').upper()}</span></div>
                    <div><b>Guardrails:</b> <span class="tech-badge">NeMo Rails</span></div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Session Actions
        st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            if st.button("New Chat", use_container_width=True):
                st.session_state.messages = []
                base = st.session_state.get("user_base") or user_id
                st.session_state.user_id = f"{base}-{uuid.uuid4().hex[:6]}"
                st.rerun()
        with col2:
            if _secret("APP_PASSWORD") and st.button("Sign Out", use_container_width=True):
                st.session_state.authed = False
                st.session_state.messages = []
                st.rerun()

        st.markdown("---")
        with st.expander("Legal & Compliance"):
            st.caption(load_legal("PRIVACY.md"))
            st.caption(load_legal("TERMS.md"))

    # ── Main Content Area ──
    st.markdown(
        f"""
        <div class="hero-container">
            <h1 class="hero-title">{ASSISTANT_NAME}</h1>
            <p class="hero-subtitle">Ask questions verified against {ASSISTANT_SCOPE}. Powered by LangGraph & Qdrant.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Suggested Prompt Starters (shown when chat is empty) ──
    if not st.session_state.messages:
        st.markdown("<h4 style='font-size: 1rem; color: #94A3B8; margin-bottom: 0.8rem;'>Suggested Inquiries:</h4>", unsafe_allow_html=True)
        col_a, col_b = st.columns(2)
        starters = [
            ("⚡ ACID Properties", "Explain the ACID properties in database transactions and how atomicity is guaranteed."),
            ("🌲 B-Tree Indexing", "How does B-Tree and B+ Tree indexing optimize search operations in relational databases?"),
            ("🔒 2-Phase Locking", "What is Two-Phase Locking (2PL) and how does it prevent concurrency conflicts?"),
            ("📊 Clustered vs Non-Clustered", "What is the difference between Clustered and Non-Clustered indexes?"),
        ]

        def _handle_starter(prompt_text):
            st.session_state.pending_prompt = prompt_text

        with col_a:
            if st.button(f"{starters[0][0]}\n\n{starters[0][1]}", key="st_0", use_container_width=True):
                st.session_state.pending_prompt = starters[0][1]
                st.rerun()
            if st.button(f"{starters[1][0]}\n\n{starters[1][1]}", key="st_1", use_container_width=True):
                st.session_state.pending_prompt = starters[1][1]
                st.rerun()

        with col_b:
            if st.button(f"{starters[2][0]}\n\n{starters[2][1]}", key="st_2", use_container_width=True):
                st.session_state.pending_prompt = starters[2][1]
                st.rerun()
            if st.button(f"{starters[3][0]}\n\n{starters[3][1]}", key="st_3", use_container_width=True):
                st.session_state.pending_prompt = starters[3][1]
                st.rerun()

    # ── Chat Message History ──
    for message in st.session_state.messages:
        role = message["role"]
        with st.chat_message(role, avatar="🧑‍💻" if role == "user" else "🤖"):
            if role == "assistant" and message.get("thinking"):
                with st.expander("🧠 Agent Internal Reasoning", expanded=False):
                    st.markdown(f"*{message['thinking']}*")

            st.markdown(message["content"])

            # Sources / Contexts
            if role == "assistant" and message.get("sources"):
                with st.expander(f"📚 Retrieved Context Sources ({len(message['sources'])})", expanded=False):
                    for i, source in enumerate(message["sources"]):
                        st.markdown(
                            f"""
                            <div class="source-box">
                                <span style="font-weight: 600; color: #60A5FA;">Source Chunk {i + 1}</span><br/>
                                {source}
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

    # ── User Input Handling ──
    input_text = st.chat_input("Ask a question about database systems or documentation...")
    prompt = input_text or st.session_state.pop("pending_prompt", None)

    if prompt:
        # Append User Message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar="🧑‍💻"):
            st.markdown(prompt)

        # Assistant Response with Live Pipeline Status
        with st.chat_message("assistant", avatar="🤖"):
            status_container = st.empty()
            with status_container.status("🧠 Agent thinking...", expanded=True) as status_box:
                status_box.write("🛡️ Evaluating intent via NeMo Guardrails...")
                time.sleep(0.1)

                try:
                    data = post_query(prompt, user_id, debug=SHOW_INTERNAL)
                except Exception as exc:
                    status_box.update(label="❌ Request Failed", state="error", expanded=False)
                    st.error(f"Error querying assistant: {exc}")
                    st.stop()

                if data.get("blocked"):
                    status_box.update(label="🛡️ Guardrails Triggered (Off-Topic / Policy)", state="complete", expanded=False)
                else:
                    status_box.update(label="✅ Reasoning & Retrieval Completed", state="complete", expanded=False)

            status_container.empty()

            raw_answer = data.get("answer") or "No answer provided."
            thinking, clean_answer = _extract_thinking(raw_answer)

            # Display Thought Process if available
            if thinking:
                with st.expander("🧠 Model Internal Reasoning", expanded=False):
                    st.markdown(f"*{thinking}*")

            # Stream clean answer
            answer_placeholder = st.empty()
            curr_text = ""
            for char in clean_answer:
                curr_text += char
                answer_placeholder.markdown(curr_text + "▌")
                time.sleep(0.003)
            answer_placeholder.markdown(clean_answer)

            # Sources
            sources = data.get("sources", [])
            if sources:
                with st.expander(f"📚 Retrieved Context Sources ({len(sources)})", expanded=False):
                    for i, source in enumerate(sources):
                        st.markdown(
                            f"""
                            <div class="source-box">
                                <span style="font-weight: 600; color: #60A5FA;">Source Chunk {i + 1}</span><br/>
                                {source}
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

            # Record in history
            st.session_state.messages.append({
                "role": "assistant",
                "content": clean_answer,
                "thinking": thinking,
                "sources": sources,
            })
