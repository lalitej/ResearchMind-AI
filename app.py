import os
import re
import hashlib

import streamlit as st
from dotenv import load_dotenv

from document_processing.pdf_reader import extract_pdf
from document_processing.url_reader import extract_research_url

from ai_engines.gemini_client import (
    summarize_with_fallback,
    generate_answer_with_fallback,
    is_cloud_deployment,
)

from research_tools.history_store import init_db, save_paper, save_summary, log_event
from research_tools.ui import apply_theme


# =========================================
# CONFIGURATION
# =========================================

load_dotenv(override=True)

APP_NAME = os.getenv("APP_NAME", "ResearchMind AI")
APP_VERSION = os.getenv("APP_VERSION", "3.0")

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.8-flash"
)

QWEN_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "qwen2.5:7b"
)

PROVIDER_GEMINI = "Google Gemini"
PROVIDER_QWEN = "Ollama - Qwen 2.5"


# =========================================
# PAGE CONFIGURATION
# =========================================

st.set_page_config(
    page_title=APP_NAME,
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()
apply_theme()


# =========================================
# EXTRACTION CACHE
# =========================================

@st.cache_data(show_spinner=False)
def cached_extract_pdf(pdf_bytes):
    return extract_pdf(pdf_bytes)


@st.cache_data(show_spinner=False)
def cached_extract_url(
    url,
    cache_version="wikipedia-cleanup-v2"
):
    return extract_research_url(url)


# =========================================
# SESSION STATE
# =========================================

defaults = {
    "messages": [],
    "paper_hash": None,
    "paper_data": None,
    "paper_summary": None,
    "summary_error": None,
    "summary_running": False,

    # Actual model that generated the summary
    "summary_model": None,

    # Provider that generated the summary
    "summary_provider": None,

    # Provider selected in the sidebar
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


# =========================================
# RESET FUNCTIONS
# =========================================

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


# =========================================
# PROVIDER DISPLAY
# =========================================

def display_provider_info(result, feature="AI response"):

    provider = result.get(
        "provider",
        "Unknown provider"
    )

    model = result.get(
        "model",
        "Unknown model"
    )

    fallback_used = result.get(
        "fallback_used",
        False
    )

    fallback_reason = result.get(
        "fallback_reason"
    )

    st.caption(
        f"Provider: {provider} | Model: {model}"
    )

    if fallback_used:

        st.warning(
            f"{feature} was generated using {provider} "
            f"because Gemini was unavailable. "
            f"Reason: {fallback_reason or 'Temporary provider issue'}."
        )


# =========================================
# PAPER TEXT RETRIEVAL
# =========================================

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
            ""
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
            ""
        )[:max_context_chars]

    scored_pages.sort(
        key=lambda item: item[0],
        reverse=True
    )

    selected_pages = scored_pages[:max_pages]

    if not any(item[0] > 0 for item in selected_pages):

        selected_pages = sorted(
            scored_pages,
            key=lambda item: item[1]
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


# =========================================
# PAPER-GROUNDED AI CHAT
# =========================================

def answer_paper_question(
    paper_data,
    question,
    chat_history,
    selected_model
):

    """
    Answer questions using retrieved research-paper content.
    Automatically falls back from Gemini to Qwen.
    """

    metadata = paper_data.get("metadata", {})

    title = metadata.get(
        "title",
        "Unknown research paper"
    )

    context = get_relevant_paper_context(
        paper_data,
        question
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
        max_output_tokens=4096
    )

    if not isinstance(result, dict):

        raise ValueError(
            "Chat fallback returned an invalid result."
        )

    return result


# =========================================
# CUSTOM CSS
# The shared design system and optional dark mode are applied by research_tools.ui.apply_theme().


# =========================================
# SIDEBAR
# =========================================

with st.sidebar:

    st.markdown("## 🧠 ResearchMind AI")

    st.caption(f"Version {APP_VERSION}")

    st.divider()

    st.markdown("### AI Configuration")

    # Local Ollama is not automatically available on Streamlit Cloud.
    cloud_mode = is_cloud_deployment()

    available_models = (
        [PROVIDER_GEMINI]
        if cloud_mode
        else [PROVIDER_GEMINI, PROVIDER_QWEN]
    )

    if (
        cloud_mode
        and st.session_state.get("selected_model") != PROVIDER_GEMINI
    ):
        st.session_state["selected_model"] = PROVIDER_GEMINI

    selected_model = st.selectbox(
        "Select AI model",
        available_models,
        key="selected_model"
    )

    # Track the selected provider separately from the
    # actual model used to generate the summary.

    if (
        st.session_state.summary_selected_provider
        != selected_model
    ):

        st.session_state.summary_selected_provider = selected_model

        reset_summary_state()

    st.caption(
        f"Gemini: {GEMINI_MODEL}"
    )

    st.caption(
        f"Local model: {QWEN_MODEL}"
    )

    st.divider()

    if st.button(
        "🗑️ Clear chat",
        use_container_width=True
    ):

        st.session_state.messages = []
        st.session_state.chat_provider = None
        st.session_state.chat_model = None

        st.rerun()

    if st.button(
        "🔄 Reset research paper",
        use_container_width=True
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


# =========================================
# HEADER
# =========================================

header_left, header_right = st.columns([5, 1])

with header_left:

    st.markdown(
        f'<div class="main-title">🧠 {APP_NAME}</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="subtitle">'
        'Your intelligent research paper companion'
        '</div>',
        unsafe_allow_html=True
    )

with header_right:

    st.markdown(
        '<span class="status">● Workspace ready</span>',
        unsafe_allow_html=True
    )

st.divider()


# =========================================
# TWO-PANEL LAYOUT
# =========================================

left_panel, right_panel = st.columns(
    [1.05, 0.95],
    gap="large"
)


# =========================================
# LEFT PANEL - RESEARCH PAPER
# =========================================

with left_panel:

    st.markdown(
        '<div class="panel-heading">📄 Research Paper</div>',
        unsafe_allow_html=True
    )

    st.caption(
        "Upload a PDF or paste a research paper URL."
    )

    input_method = st.radio(
        "Choose research paper source",
        [
            "Upload PDF",
            "Paper URL"
        ],
        horizontal=True,
        key="paper_input_method"
    )

    previous_method = st.session_state.previous_input_method

    if previous_method != input_method:

        reset_paper_state()

        st.session_state.previous_input_method = input_method

    paper_data = st.session_state.paper_data

    # =====================================
    # OPTION 1: UPLOAD PDF
    # =====================================

    if input_method == "Upload PDF":

        uploaded_file = st.file_uploader(
            "Import research paper",
            type=["pdf"],
            key="research_pdf"
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
                        "Uploaded PDF"
                    )

                    st.session_state.paper_data = extracted_data
                    st.session_state.paper_record_id = save_paper(extracted_data, file_hash)
                    log_event("paper_import", "Research paper imported", extracted_data.get("source_type", "Uploaded PDF"), paper_id=st.session_state.paper_record_id)

                    paper_data = extracted_data

                except Exception as error:

                    st.session_state.paper_hash = None
                    st.session_state.summary_error = str(error)

                    paper_data = None

    # =====================================
    # OPTION 2: RESEARCH PAPER URL
    # =====================================

    else:

        with st.form("research_url_form"):

            research_url = st.text_input(
                "Research paper URL",
                placeholder="https://arxiv.org/abs/1706.03762",
                help=(
                    "Supports direct PDF links, arXiv HTML "
                    "pages and article webpages."
                )
            )

            submitted = st.form_submit_button(
                "🌐 Fetch Research Paper",
                use_container_width=True
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
    cache_version="wikipedia-cleanup-v2"
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
                        st.session_state.paper_record_id = save_paper(extracted_data, url_hash)
                        log_event("paper_import", "Research paper imported", extracted_data.get("source_type", "Research URL"), paper_id=st.session_state.paper_record_id)

                        paper_data = extracted_data

                    except Exception as error:

                        st.session_state.paper_hash = None
                        st.session_state.summary_error = str(error)

                        paper_data = None

                else:

                    paper_data = st.session_state.paper_data

    # =====================================
    # REFRESH PAPER DATA
    # =====================================

    paper_data = st.session_state.paper_data

    # =====================================
    # DISPLAY ERRORS
    # =====================================

    if st.session_state.summary_error and paper_data is None:

        st.error(
            st.session_state.summary_error
        )

    # =====================================
    # DISPLAY PAPER INFORMATION
    # =====================================

    if paper_data is not None and paper_data.get("success"):

        metadata = paper_data.get("metadata", {})

        st.success(
            "Research paper imported successfully!"
        )

        st.markdown("### 📑 Document Overview")

        st.write(
            f"**Title:** {metadata.get('title', 'Unknown title')}"
        )

        st.write(
            f"**Author:** {metadata.get('author', 'Unknown author')}"
        )

        source_type = paper_data.get(
            "source_type",
            "Research document"
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
            paper_data.get("total_pages", 1)
        )

        col2.metric(
            "Extracted Words",
            f"{paper_data.get('total_words', 0):,}"
        )

        for warning in paper_data.get("warnings", []):

            st.warning(warning)

        st.divider()

        st.markdown(
            "### ✨ Automatic Research Summary"
        )

        # =================================
        # GENERATE RESEARCH SUMMARY
        # =================================

        if (
            st.session_state.paper_summary is None
            and st.session_state.summary_error is None
            and not st.session_state.summary_running
        ):

            # Lock summary generation to avoid
            # duplicate execution in this session.

            st.session_state.summary_running = True

            progress_bar = None

            try:

                progress_bar = st.progress(0)

                def update_progress(value):

                    percentage = int(float(value) * 100)

                    percentage = max(
                        0,
                        min(100, percentage)
                    )

                    progress_bar.progress(percentage)

                with st.spinner(
                    "ResearchMind AI is analyzing your research paper..."
                ):

                    result = summarize_with_fallback(
                        paper_data=paper_data,
                        preferred_provider=selected_model,
                        progress_callback=update_progress
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
                    save_summary(st.session_state.paper_record_id, str(summary))
                    log_event("summary", "Research summary generated", f"{result.get('provider', 'Unknown provider')} / {result.get('model', 'Unknown model')}", str(summary), st.session_state.paper_record_id)

                st.session_state.summary_provider = result.get(
                    "provider",
                    "Unknown provider"
                )

                # Store the ACTUAL model used,
                # not the sidebar provider selection.

                st.session_state.summary_model = result.get(
                    "model",
                    "Unknown model"
                )

                st.session_state.summary_fallback_used = result.get(
                    "fallback_used",
                    False
                )

                st.session_state.summary_fallback_reason = result.get(
                    "fallback_reason"
                )

                st.session_state.summary_error = None

            except Exception as error:

                import traceback

                print("\n========== RESEARCH SUMMARY ERROR ==========")
                print(f"Error type: {type(error).__name__}")
                print(f"Error message: {error}")
                traceback.print_exc()
                print("============================================\n")

                st.session_state.summary_error = str(error)

            finally:

                if progress_bar is not None:
                    progress_bar.empty()

                # Always release the lock,
                # whether summary generation succeeds or fails.

                st.session_state.summary_running = False

        # =================================
        # DISPLAY SUMMARY
        # =================================

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
                flags=re.IGNORECASE
            )

            summary_text = re.sub(
                r"\n```\s*$",
                "",
                summary_text
            )

            st.markdown(
                summary_text,
                unsafe_allow_html=False
            )

        elif st.session_state.summary_error:

            st.error(st.session_state.summary_error)

            if st.button("🔄 Retry summary generation"):

                st.session_state.summary_error = None
                st.session_state.summary_running = False

                st.rerun()

        # =================================
        # EXTRACTED RESEARCH TEXT
        # =================================

        with st.expander("📖 View extracted research text"):

            full_text = paper_data.get("full_text", "")

            if not full_text and paper_data.get("pages"):

                full_text = "\n\n".join(
                    f"[PAGE {page.get('page_number', 1)}]\n"
                    f"{page.get('text', '')}"
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

    # =====================================
    # WELCOME SCREEN
    # =====================================

    elif paper_data is None and not st.session_state.summary_error:

        st.markdown(
            """
            ### Welcome to ResearchMind AI

            Import a research paper to begin.

            Your workspace will help you:

            - Understand complex research papers.
            - Generate structured summaries.
            - Explore research methodologies.
            - Identify research contributions.
            - Analyze academic publications.
            """
        )


# =========================================
# RIGHT PANEL - AI ASSISTANT
# =========================================

with right_panel:

    st.markdown(
        '<div class="panel-heading">🤖 AI Research Assistant</div>',
        unsafe_allow_html=True
    )

    st.caption(
        "Your personal research discussion space."
    )

    st.markdown(
        f'<span class="status">● Selected model: {selected_model}</span>',
        unsafe_allow_html=True
    )

    if st.session_state.paper_data is None:

        st.info(
            "Import a research paper to start "
            "your research conversation."
        )

    else:

        st.markdown(
            "### Ask about your research paper"
        )

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

        question = st.chat_input(
            "Ask anything about this research paper..."
        )

        if question:

            st.session_state.messages.append(
                {
                    "role": "user",
                    "content": question
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
                        selected_model=selected_model
                    )

                answer = result.get("text", "")

                if not answer or not str(answer).strip():

                    raise ValueError(
                        "The AI model returned an empty response."
                    )

                provider = result.get(
                    "provider",
                    "Unknown provider"
                )

                model = result.get(
                    "model",
                    "Unknown model"
                )

                fallback_used = result.get(
                    "fallback_used",
                    False
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

            if st.session_state.paper_record_id:
                log_event("question", "Question asked", question, question, st.session_state.paper_record_id)
                log_event("answer", "AI answer viewed", f"Provider: {provider or 'Unavailable'}", str(answer), st.session_state.paper_record_id)

            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": str(answer),
                    "provider": provider,
                    "model": model,
                    "fallback_used": fallback_used,
                    "fallback_reason": fallback_reason
                }
            )

            st.rerun()

        st.caption(
            "Answers use retrieved paper content. "
            "Page references are included where supported."
        )


# =========================================
# FOOTER
# =========================================

st.divider()

st.caption(
    f"ResearchMind AI v{APP_VERSION} | "
    "Gemini + Ollama Hybrid Architecture"
)