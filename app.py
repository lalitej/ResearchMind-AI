import os
import re
import hashlib
import traceback

import streamlit as st
from dotenv import load_dotenv

from document_processing.pdf_reader import extract_pdf
from document_processing.url_reader import extract_research_url

from ai_engines.gemini_client import (
    summarize_with_fallback,
    generate_answer_with_fallback,
)

from research_tools.history_store import (
    init_db,
    save_paper,
    save_summary,
    log_event,
)

from research_tools.ui import apply_theme, page_header


# =========================================================
# CONFIGURATION
# =========================================================

load_dotenv(override=True)

APP_NAME = os.getenv("APP_NAME", "ResearchMind AI")
APP_VERSION = os.getenv("APP_VERSION", "3.0")

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.8-flash",
)

QWEN_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "qwen2.5:7b",
)

PROVIDER_GEMINI = "Google Gemini"
PROVIDER_QWEN = "Ollama - Qwen 2.5"


# =========================================================
# PAGE CONFIGURATION
# =========================================================

st.set_page_config(
    page_title=APP_NAME,
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()
apply_theme()


# =========================================================
# EXTRA DESIGN POLISH
# =========================================================

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.8rem;
        padding-bottom: 2rem;
        max-width: 1500px;
    }

    .rm-section-label {
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.13em;
        text-transform: uppercase;
        color: var(--text-color);
        opacity: 0.62;
        margin-bottom: 0.35rem;
    }

    .rm-section-title {
        font-size: 1.25rem;
        font-weight: 700;
        letter-spacing: -0.025em;
        margin-bottom: 0.25rem;
    }

    .rm-section-description {
        font-size: 0.88rem;
        opacity: 0.7;
        margin-bottom: 1rem;
    }

    .rm-status {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        border: 1px solid rgba(85, 185, 168, 0.30);
        background: rgba(85, 185, 168, 0.09);
        color: #55B9A8;
        padding: 0.4rem 0.75rem;
        border-radius: 999px;
        font-size: 0.76rem;
        font-weight: 650;
        white-space: nowrap;
    }

    .rm-status-dot {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: #55B9A8;
        display: inline-block;
    }

    .rm-document-title {
        font-size: 1.05rem;
        font-weight: 700;
        line-height: 1.5;
        margin-top: 0.3rem;
        margin-bottom: 0.8rem;
    }

    .rm-empty-state {
        border: 1px dashed rgba(140, 160, 180, 0.35);
        border-radius: 14px;
        padding: 1.5rem;
        text-align: center;
        margin-top: 0.8rem;
        margin-bottom: 0.8rem;
    }

    .rm-empty-icon {
        font-size: 2rem;
        margin-bottom: 0.5rem;
    }

    .rm-empty-title {
        font-size: 1rem;
        font-weight: 700;
        margin-bottom: 0.35rem;
    }

    .rm-empty-description {
        font-size: 0.84rem;
        opacity: 0.68;
        line-height: 1.6;
    }

    .rm-footer {
        text-align: center;
        font-size: 0.78rem;
        opacity: 0.55;
        padding-top: 0.5rem;
        padding-bottom: 0.5rem;
    }

    div[data-testid="stMetric"] {
        border-radius: 12px;
        padding: 0.75rem;
        border: 1px solid rgba(140, 160, 180, 0.16);
    }

    div[data-testid="stChatMessage"] {
        border-radius: 12px;
    }

    @media (max-width: 900px) {
        .block-container {
            padding-left: 1rem;
            padding-right: 1rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# EXTRACTION CACHE
# =========================================================

@st.cache_data(show_spinner=False)
def cached_extract_pdf(pdf_bytes):
    return extract_pdf(pdf_bytes)


@st.cache_data(show_spinner=False)
def cached_extract_url(
    url,
    cache_version="wikipedia-cleanup-v2",
):
    return extract_research_url(url)


# =========================================================
# SESSION STATE
# =========================================================

defaults = {
    "messages": [],
    "paper_hash": None,
    "paper_data": None,
    "paper_summary": None,
    "summary_error": None,
    "summary_running": False,

    "summary_model": None,
    "summary_provider": None,
    "summary_selected_provider": None,

    "summary_fallback_used": False,
    "summary_fallback_reason": None,

    "chat_provider": None,
    "chat_model": None,

    "previous_input_method": None,
    "paper_record_id": None,
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# =========================================================
# RESET FUNCTIONS
# =========================================================

def reset_paper_state():

    st.session_state.paper_hash = None
    st.session_state.paper_record_id = None
    st.session_state.paper_data = None
    st.session_state.paper_summary = None
    st.session_state.summary_error = None
    st.session_state.summary_running = False

    st.session_state.summary_model = None
    st.session_state.summary_provider = None

    st.session_state.summary_fallback_used = False
    st.session_state.summary_fallback_reason = None

    st.session_state.chat_provider = None
    st.session_state.chat_model = None

    st.session_state.messages = []


def reset_summary_state():

    st.session_state.paper_summary = None
    st.session_state.summary_error = None
    st.session_state.summary_running = False

    st.session_state.summary_model = None
    st.session_state.summary_provider = None

    st.session_state.summary_fallback_used = False
    st.session_state.summary_fallback_reason = None


# =========================================================
# PAPER TEXT RETRIEVAL
# =========================================================

def get_relevant_paper_context(
    paper_data,
    question,
    max_pages=8,
    max_context_chars=24000,
):
    """
    Retrieve relevant extracted pages using keyword matching.
    """

    pages = paper_data.get("pages", [])

    if not pages:
        return paper_data.get(
            "full_text",
            "",
        )[:max_context_chars]

    question_words = {
        word.lower().strip(".,?!:;()[]{}\\\"'")
        for word in question.split()
        if len(word) > 2
    }

    scored_pages = []

    for page in pages:

        if not isinstance(page, dict):
            continue

        page_text = page.get("text", "")

        if not page_text or not page_text.strip():
            continue

        page_number = page.get("page_number", 1)

        page_lower = page_text.lower()

        score = sum(
            page_lower.count(word)
            for word in question_words
        )

        scored_pages.append(
            (score, page_number, page_text)
        )

    if not scored_pages:
        return paper_data.get(
            "full_text",
            "",
        )[:max_context_chars]

    scored_pages.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    selected_pages = scored_pages[:max_pages]

    if not any(item[0] > 0 for item in selected_pages):

        selected_pages = sorted(
            scored_pages,
            key=lambda item: item[1],
        )[:max_pages]

    selected_pages.sort(
        key=lambda item: item[1]
    )

    context_parts = []
    total_chars = 0

    for score, page_number, page_text in selected_pages:

        remaining = max_context_chars - total_chars

        if remaining <= 0:
            break

        page_text = page_text[:remaining]

        context_parts.append(
            f"[PAGE {page_number}]\n{page_text}"
        )

        total_chars += len(page_text)

    return "\n\n".join(context_parts)


# =========================================================
# PAPER-GROUNDED AI CHAT
# =========================================================

def answer_paper_question(
    paper_data,
    question,
    chat_history,
    selected_model,
):
    """
    Answer questions using retrieved research-paper content.
    Automatically uses the configured provider fallback.
    """

    metadata = paper_data.get("metadata", {})

    title = metadata.get(
        "title",
        "Unknown research paper",
    )

    context = get_relevant_paper_context(
        paper_data,
        question,
    )

    if not context.strip():
        raise ValueError(
            "No extracted paper text is available."
        )

    history_text = ""

    for message in chat_history[-6:]:

        role = message.get("role", "user")
        content = message.get("content", "")

        history_text += (
            f"\n{role.upper()}: {content}\n"
        )

    prompt = f"""
You are ResearchMind AI, an academic research assistant.

Answer the user's question using the supplied extracted
research paper context.

PAPER TITLE:
{title}

STRICT RULES:

1. Base factual answers only on the supplied paper context.
2. Do not invent facts, results, numbers, authors or methods.
3. Include page references such as [Page 2] when supported.
4. If the answer is not present in the retrieved context,
   clearly say that you could not find it in the retrieved
   paper sections.
5. Do not use outside knowledge to fill missing paper details.
6. Distinguish the authors' claims from your own explanation.
7. Explain technical concepts in simple language.
8. Preserve exact numerical values and units.
9. Never invent page numbers.
10. Answer follow-up questions using the conversation history,
    but keep factual claims grounded in the supplied paper.

RECENT CONVERSATION:
{history_text}

RETRIEVED PAPER CONTEXT:
{context}

USER QUESTION:
{question}

Provide a helpful, evidence-grounded answer.
"""

    result = generate_answer_with_fallback(
        prompt=prompt,
        preferred_provider=selected_model,
        max_output_tokens=4096,
    )

    if not isinstance(result, dict):
        raise ValueError(
            "Chat fallback returned an invalid result."
        )

    return result


# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:

    st.markdown("## 🧠 ResearchMind AI")

    st.caption(f"Version {APP_VERSION}")

    st.divider()

    st.markdown("### AI Configuration")

    available_models = [
        PROVIDER_GEMINI,
        PROVIDER_QWEN,
    ]

    selected_model = st.selectbox(
        "Select AI model",
        available_models,
        key="selected_model",
    )

    if (
        st.session_state.summary_selected_provider
        != selected_model
    ):

        st.session_state.summary_selected_provider = selected_model

        reset_summary_state()

    st.caption(f"Gemini model: {GEMINI_MODEL}")

    st.caption(f"Ollama model: {QWEN_MODEL}")

    st.divider()

    st.markdown("### Workspace controls")

    if st.button(
        "🗑️ Clear chat",
        use_container_width=True,
    ):

        st.session_state.messages = []
        st.session_state.chat_provider = None
        st.session_state.chat_model = None

        st.rerun()

    if st.button(
        "🔄 Reset research paper",
        use_container_width=True,
    ):

        reset_paper_state()

        st.rerun()

    st.divider()

    st.markdown("### About")

    st.caption(
        "An intelligent research companion "
        "for understanding academic papers."
    )

    st.caption(
        "Supports PDF documents, research URLs "
        "and web articles."
    )

    st.divider()

    st.caption("Powered by Gemini + Ollama")


# =========================================================
# MAIN HEADER
# =========================================================

page_header(
    eyebrow="AI-POWERED RESEARCH WORKSPACE",
    title=APP_NAME,
    subtitle=(
        "Understand academic papers, generate structured "
        "summaries and explore research with AI."
    ),
)

st.markdown(
    """
    <div style="margin-top: 0.5rem; margin-bottom: 1.2rem;">
        <span class="rm-status">
            <span class="rm-status-dot"></span>
            Research workspace ready
        </span>
    </div>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# TWO-PANEL WORKSPACE
# =========================================================

left_panel, right_panel = st.columns(
    [1.05, 0.95],
    gap="large",
)


# =========================================================
# LEFT PANEL - RESEARCH PAPER
# =========================================================

with left_panel:

    st.markdown(
        """
        <div class="rm-section-label">DOCUMENT WORKSPACE</div>
        <div class="rm-section-title">📄 Research Paper</div>
        <div class="rm-section-description">
            Import a research paper to extract, analyze and summarize its content.
        </div>
        """,
        unsafe_allow_html=True,
    )

    input_method = st.radio(
        "Choose research paper source",
        [
            "Upload PDF",
            "Paper URL",
        ],
        horizontal=True,
        key="paper_input_method",
    )

    previous_method = st.session_state.previous_input_method

    if previous_method != input_method:

        reset_paper_state()

        st.session_state.previous_input_method = input_method

    paper_data = st.session_state.paper_data

    # -----------------------------------------------------
    # OPTION 1: UPLOAD PDF
    # -----------------------------------------------------

    if input_method == "Upload PDF":

        uploaded_file = st.file_uploader(
            "Import research paper",
            type=["pdf"],
            key="research_pdf",
            help="Upload a PDF containing selectable research text.",
        )

        if uploaded_file is not None:

            pdf_bytes = uploaded_file.getvalue()

            file_hash = hashlib.sha256(
                pdf_bytes
            ).hexdigest()

            if file_hash != st.session_state.paper_hash:

                reset_paper_state()

                st.session_state.paper_hash = file_hash

                try:

                    with st.spinner(
                        "Extracting PDF content..."
                    ):

                        extracted_data = cached_extract_pdf(
                            pdf_bytes
                        )

                    if not isinstance(extracted_data, dict):
                        raise ValueError(
                            "PDF reader returned invalid data."
                        )

                    if not extracted_data.get("success"):
                        raise ValueError(
                            "No readable text was extracted from this PDF."
                        )

                    extracted_data.setdefault(
                        "source_type",
                        "Uploaded PDF",
                    )

                    st.session_state.paper_data = extracted_data

                    st.session_state.paper_record_id = save_paper(
                        extracted_data,
                        file_hash,
                    )

                    log_event(
                        "paper_import",
                        "Research paper imported",
                        extracted_data.get(
                            "source_type",
                            "Uploaded PDF",
                        ),
                        paper_id=st.session_state.paper_record_id,
                    )

                    paper_data = extracted_data

                except Exception as error:

                    st.session_state.paper_hash = None
                    st.session_state.summary_error = str(error)

                    paper_data = None

    # -----------------------------------------------------
    # OPTION 2: RESEARCH PAPER URL
    # -----------------------------------------------------

    else:

        with st.form("research_url_form"):

            research_url = st.text_input(
                "Research paper URL",
                placeholder="https://arxiv.org/abs/1706.03762",
                help=(
                    "Supports direct PDF links, arXiv HTML "
                    "pages and article webpages."
                ),
            )

            submitted = st.form_submit_button(
                "🌐 Fetch Research Paper",
                use_container_width=True,
            )

        if submitted:

            if not research_url.strip():

                st.warning(
                    "Please enter a research paper URL."
                )

            else:

                research_url = research_url.strip()

                url_hash = hashlib.sha256(
                    research_url.encode("utf-8")
                ).hexdigest()

                if (
                    url_hash != st.session_state.paper_hash
                    or st.session_state.paper_data is None
                ):

                    reset_paper_state()

                    st.session_state.paper_hash = url_hash

                    try:

                        with st.spinner(
                            "Fetching and extracting research paper..."
                        ):

                            extracted_data = cached_extract_url(
                                research_url,
                                cache_version="wikipedia-cleanup-v2",
                            )

                        if not isinstance(extracted_data, dict):
                            raise ValueError(
                                "URL reader returned invalid data."
                            )

                        if not extracted_data.get("success"):
                            raise ValueError(
                                "No readable research paper content was found."
                            )

                        st.session_state.paper_data = extracted_data

                        st.session_state.paper_record_id = save_paper(
                            extracted_data,
                            url_hash,
                        )

                        log_event(
                            "paper_import",
                            "Research paper imported",
                            extracted_data.get(
                                "source_type",
                                "Research URL",
                            ),
                            paper_id=st.session_state.paper_record_id,
                        )

                        paper_data = extracted_data

                    except Exception as error:

                        st.session_state.paper_hash = None
                        st.session_state.summary_error = str(error)

                        paper_data = None

                else:

                    paper_data = st.session_state.paper_data

    # -----------------------------------------------------
    # REFRESH PAPER DATA
    # -----------------------------------------------------

    paper_data = st.session_state.paper_data

    # -----------------------------------------------------
    # DISPLAY ERRORS
    # -----------------------------------------------------

    if st.session_state.summary_error and paper_data is None:

        st.error(
            st.session_state.summary_error
        )

    # -----------------------------------------------------
    # DISPLAY PAPER INFORMATION
    # -----------------------------------------------------

    if paper_data is not None and paper_data.get("success"):

        metadata = paper_data.get("metadata", {})

        st.success(
            "Research paper imported successfully!"
        )

        st.markdown(
            """
            <div class="rm-section-label">DOCUMENT INFORMATION</div>
            <div class="rm-section-title">📑 Document Overview</div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            f"""
            <div class="rm-document-title">
                {metadata.get("title", "Unknown title")}
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.write(
            f"**Author:** {metadata.get('author', 'Unknown author')}"
        )

        source_type = paper_data.get(
            "source_type",
            "Research document",
        )

        st.caption(f"Source: {source_type}")

        source_url = paper_data.get("source_url", "")

        if source_url:

            st.markdown(
                f"[Open original research paper]({source_url})"
            )

        col1, col2 = st.columns(2)

        col1.metric(
            "Total Pages",
            paper_data.get("total_pages", 1),
        )

        col2.metric(
            "Extracted Words",
            f"{paper_data.get('total_words', 0):,}",
        )

        for warning in paper_data.get("warnings", []):

            st.warning(warning)

        st.divider()

        # -------------------------------------------------
        # AUTOMATIC RESEARCH SUMMARY
        # -------------------------------------------------

        st.markdown(
            """
            <div class="rm-section-label">AI ANALYSIS</div>
            <div class="rm-section-title">✨ Automatic Research Summary</div>
            <div class="rm-section-description">
                A structured overview generated from your imported paper.
            </div>
            """,
            unsafe_allow_html=True,
        )

        if (
            st.session_state.paper_summary is None
            and st.session_state.summary_error is None
            and not st.session_state.summary_running
        ):

            st.session_state.summary_running = True

            progress_bar = None

            try:

                progress_bar = st.progress(0)

                def update_progress(value):

                    percentage = int(float(value) * 100)

                    percentage = max(
                        0,
                        min(100, percentage),
                    )

                    progress_bar.progress(percentage)

                with st.spinner(
                    "ResearchMind AI is analyzing your research paper..."
                ):

                    result = summarize_with_fallback(
                        paper_data=paper_data,
                        preferred_provider=selected_model,
                        progress_callback=update_progress,
                    )

                if not isinstance(result, dict):
                    raise ValueError(
                        "Summary fallback returned an invalid result."
                    )

                summary = result.get("text", "")

                if not summary or not str(summary).strip():
                    raise ValueError(
                        "The AI model returned an empty summary."
                    )

                st.session_state.paper_summary = str(summary)

                if st.session_state.paper_record_id:

                    save_summary(
                        st.session_state.paper_record_id,
                        str(summary),
                    )

                    log_event(
                        "summary",
                        "Research summary generated",
                        (
                            f"{result.get('provider', 'Unknown provider')} / "
                            f"{result.get('model', 'Unknown model')}"
                        ),
                        str(summary),
                        st.session_state.paper_record_id,
                    )

                st.session_state.summary_provider = result.get(
                    "provider",
                    "Unknown provider",
                )

                st.session_state.summary_model = result.get(
                    "model",
                    "Unknown model",
                )

                st.session_state.summary_fallback_used = result.get(
                    "fallback_used",
                    False,
                )

                st.session_state.summary_fallback_reason = result.get(
                    "fallback_reason"
                )

                st.session_state.summary_error = None

            except Exception as error:

                print("\n========== RESEARCH SUMMARY ERROR ==========")
                print(f"Error type: {type(error).__name__}")
                print(f"Error message: {error}")
                traceback.print_exc()
                print("============================================\n")

                st.session_state.summary_error = str(error)

            finally:

                if progress_bar is not None:
                    progress_bar.empty()

                st.session_state.summary_running = False

        # -------------------------------------------------
        # DISPLAY SUMMARY
        # -------------------------------------------------

        if st.session_state.paper_summary:

            st.caption(
                f"Provider: {st.session_state.summary_provider} | "
                f"Model: {st.session_state.summary_model}"
            )

            if st.session_state.summary_fallback_used:

                st.warning(
                    "Gemini was unavailable. "
                    "Qwen generated this summary instead. "
                    f"Reason: {st.session_state.summary_fallback_reason}"
                )

            summary_text = str(
                st.session_state.paper_summary
            ).strip()

            summary_text = re.sub(
                r"^\s*```(?:markdown|md|text)?\s*\n",
                "",
                summary_text,
                flags=re.IGNORECASE,
            )

            summary_text = re.sub(
                r"\n```\s*$",
                "",
                summary_text,
            )

            st.markdown(
                summary_text,
                unsafe_allow_html=False,
            )

        elif st.session_state.summary_error:

            st.error(
                st.session_state.summary_error
            )

            if st.button(
                "🔄 Retry summary generation",
                use_container_width=True,
            ):

                st.session_state.summary_error = None
                st.session_state.summary_running = False

                st.rerun()

        # -------------------------------------------------
        # EXTRACTED RESEARCH TEXT
        # -------------------------------------------------

        with st.expander("📖 View extracted research text"):

            full_text = paper_data.get("full_text", "")

            if not full_text and paper_data.get("pages"):

                full_text = "\n\n".join(
                    (
                        f"[PAGE {page.get('page_number', 1)}]\n"
                        f"{page.get('text', '')}"
                    )
                    for page in paper_data["pages"]
                    if isinstance(page, dict)
                )

            st.text(
                full_text[:10000]
            )

            if len(full_text) > 10000:

                st.caption(
                    "Showing the first 10,000 characters."
                )

    # -----------------------------------------------------
    # WELCOME SCREEN
    # -----------------------------------------------------

    elif paper_data is None and not st.session_state.summary_error:

        st.markdown(
            """
            <div class="rm-empty-state">
                <div class="rm-empty-icon">📚</div>
                <div class="rm-empty-title">
                    Welcome to ResearchMind AI
                </div>
                <div class="rm-empty-description">
                    Import a research paper to begin your workspace.
                    <br><br>
                    Generate structured summaries, understand
                    methodologies, identify research contributions
                    and explore academic publications.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# =========================================================
# RIGHT PANEL - AI RESEARCH ASSISTANT
# =========================================================

with right_panel:

    st.markdown(
        """
        <div class="rm-section-label">INTERACTIVE AI WORKSPACE</div>
        <div class="rm-section-title">🤖 AI Research Assistant</div>
        <div class="rm-section-description">
            Ask questions and explore the contents of your research paper.
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <span class="rm-status">
            <span class="rm-status-dot"></span>
            Selected model: {selected_model}
        </span>
        """,
        unsafe_allow_html=True,
    )

    st.write("")

    if st.session_state.paper_data is None:

        st.markdown(
            """
            <div class="rm-empty-state">
                <div class="rm-empty-icon">💬</div>
                <div class="rm-empty-title">
                    Your research conversation starts here
                </div>
                <div class="rm-empty-description">
                    Import a research paper to ask questions,
                    understand findings and explore its methodology.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    else:

        st.markdown("### Ask about your research paper")

        # -------------------------------------------------
        # DISPLAY CHAT HISTORY
        # -------------------------------------------------

        for message in st.session_state.messages:

            with st.chat_message(message["role"]):

                st.markdown(
                    message["content"]
                )

                if message.get("provider"):

                    st.caption(
                        f"Provider: {message['provider']} | "
                        f"Model: {message.get('model', 'Unknown')}"
                    )

                if message.get("fallback_used"):

                    st.warning(
                        "Gemini was unavailable. "
                        "This answer was generated using Qwen."
                    )

        # -------------------------------------------------
        # CHAT INPUT
        # -------------------------------------------------

        question = st.chat_input(
            "Ask anything about this research paper..."
        )

        if question:

            st.session_state.messages.append(
                {
                    "role": "user",
                    "content": question,
                }
            )

            try:

                with st.spinner(
                    f"{selected_model} is analyzing the paper..."
                ):

                    result = answer_paper_question(
                        paper_data=st.session_state.paper_data,
                        question=question,
                        chat_history=st.session_state.messages[:-1],
                        selected_model=selected_model,
                    )

                answer = result.get("text", "")

                if not answer or not str(answer).strip():
                    raise ValueError(
                        "The AI model returned an empty response."
                    )

                provider = result.get(
                    "provider",
                    "Unknown provider",
                )

                model = result.get(
                    "model",
                    "Unknown model",
                )

                fallback_used = result.get(
                    "fallback_used",
                    False,
                )

                fallback_reason = result.get(
                    "fallback_reason"
                )

                st.session_state.chat_provider = provider
                st.session_state.chat_model = model

            except Exception as error:

                answer = (
                    "Sorry, I couldn't answer that question.\n\n"
                    f"**Error:** {error}"
                )

                provider = None
                model = None
                fallback_used = False
                fallback_reason = None

            # ---------------------------------------------
            # SAVE CHAT ACTIVITY
            # ---------------------------------------------

            if st.session_state.paper_record_id:

                log_event(
                    "question",
                    "Question asked",
                    question,
                    question,
                    st.session_state.paper_record_id,
                )

                log_event(
                    "answer",
                    "AI answer viewed",
                    f"Provider: {provider or 'Unavailable'}",
                    str(answer),
                    st.session_state.paper_record_id,
                )

            # ---------------------------------------------
            # SAVE ASSISTANT MESSAGE
            # ---------------------------------------------

            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": str(answer),
                    "provider": provider,
                    "model": model,
                    "fallback_used": fallback_used,
                    "fallback_reason": fallback_reason,
                }
            )

            st.rerun()

        st.caption(
            "Answers use retrieved paper content. "
            "Page references are included where supported."
        )


# =========================================================
# FOOTER
# =========================================================

st.divider()

st.markdown(
    f"""
    <div class="rm-footer">
        ResearchMind AI v{APP_VERSION}
        &nbsp;•&nbsp;
        Gemini + Ollama Hybrid Architecture
        &nbsp;•&nbsp;
        Built for academic research
    </div>
    """,
    unsafe_allow_html=True,
)
