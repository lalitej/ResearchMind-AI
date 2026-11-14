import os
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
from google import genai
from google.genai import types

from ai_engines.ollama_client import (
    chat_with_ollama,
    OllamaError,
    OLLAMA_NUM_CTX,
    OLLAMA_MODEL,
)

load_dotenv(override=True)

# =====================================================
# 1. CONFIGURATION
# =====================================================

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
QWEN_MODEL = OLLAMA_MODEL

PROVIDER_GEMINI = "Google Gemini"
PROVIDER_QWEN = "Ollama - Qwen 2.5"


def is_cloud_deployment():
    """Detect explicit cloud deployment configuration."""
    value = os.getenv("RESEARCHMIND_CLOUD", "").strip().lower()

    if not value:
        try:
            import streamlit as st
            value = str(
                st.secrets.get("RESEARCHMIND_CLOUD", "false")
            ).strip().lower()
        except Exception:
            value = "false"

    return value in ("1", "true", "yes", "on")

MAX_DIRECT_CHARS = 28000
MAX_CHUNK_CHARS = 30000
MAX_WORKERS = 3
MAX_ATTEMPTS = 3

GEMINI_OUTPUT_TOKENS = 8192
CHUNK_OUTPUT_TOKENS = 4096
TEMPERATURE = 0.1


def _read_int_env(name, default):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


VERIFY_SUMMARY = os.getenv(
    "GEMINI_VERIFY_SUMMARY",
    "true"
).strip().lower() in ("1", "true", "yes", "on")

QUOTA_COOLDOWN_SECONDS = _read_int_env(
    "GEMINI_QUOTA_COOLDOWN_SECONDS",
    3600
)

RATE_LIMIT_COOLDOWN_SECONDS = 60

QWEN_NUM_CTX = OLLAMA_NUM_CTX

QWEN_CHUNK_CHARS = _read_int_env(
    "QWEN_CHUNK_CHARS",
    5000
)

QWEN_FINAL_EVIDENCE_CHARS = _read_int_env(
    "QWEN_FINAL_EVIDENCE_CHARS",
    16000
)

QWEN_CHUNK_OUTPUT_TOKENS = _read_int_env(
    "QWEN_CHUNK_OUTPUT_TOKENS",
    6144
)

QWEN_CONDENSE_OUTPUT_TOKENS = _read_int_env(
    "QWEN_CONDENSE_OUTPUT_TOKENS",
    4096
)

QWEN_FINAL_OUTPUT_TOKENS = _read_int_env(
    "QWEN_FINAL_OUTPUT_TOKENS",
    6144
)

VERIFICATION_SKIPPED_NOTE = (
    "\n\n---\n\n"
    "> **Note:** Automatic evidence verification was skipped "
    "because Gemini became unavailable. This report was not "
    "checked against the original paper text.\n"
)

# =====================================================
# 2. ERROR CLASSIFICATION AND GEMINI COOLDOWN
# =====================================================


class GeminiUnavailableError(RuntimeError):

    def __init__(self, reason, message, retry_after=None):
        super().__init__(message)
        self.reason = reason
        self.retry_after = retry_after


class AllProvidersFailedError(RuntimeError):

    def __init__(self, gemini_error, qwen_error):
        self.gemini_error = gemini_error
        self.qwen_error = qwen_error

        super().__init__(
            "Both AI providers failed.\n\n"
            f"{PROVIDER_GEMINI}: {gemini_error}\n\n"
            f"{PROVIDER_QWEN}: {qwen_error}"
        )


_DAILY_QUOTA_MARKERS = (
    "perday",
    "per day",
    "requests_per_day",
    "daily",
)

_NETWORK_MARKERS = (
    "connection",
    "timed out",
    "timeout",
    "name resolution",
    "getaddrinfo",
    "network is unreachable",
    "temporary failure in name resolution",
)

_NETWORK_MODULES = (
    "httpx",
    "httpcore",
    "requests",
    "urllib3",
    "socket",
    "ssl",
)


def _error_text(error):
    parts = [str(error)]

    for attribute in ("message", "details"):
        value = getattr(error, attribute, None)

        if value:
            parts.append(str(value))

    return " ".join(parts).lower()


def _parse_retry_delay(text):
    patterns = (
        r"retrydelay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s",
        r"retry in (\d+(?:\.\d+)?)\s*s",
    )

    for pattern in patterns:
        match = re.search(pattern, text)

        if match:
            return float(match.group(1))

    return None


def classify_gemini_error(error):

    if isinstance(error, GeminiUnavailableError):
        return error.reason, error.retry_after

    if isinstance(
        error,
        (ValueError, TypeError, KeyError, AttributeError)
    ):
        return None

    text = _error_text(error)

    code = getattr(error, "code", None)
    code = code if isinstance(code, int) else None

    status = str(
        getattr(error, "status", "") or ""
    ).upper()

    retry_delay = _parse_retry_delay(text)

    is_quota_error = (
        code == 429
        or status == "RESOURCE_EXHAUSTED"
        or "resource_exhausted" in text
    )

    if is_quota_error:

        daily = (
            any(
                marker in text
                for marker in _DAILY_QUOTA_MARKERS
            )
            or re.search(r"limit:\s*0\b", text) is not None
        )

        if daily:
            return "quota_exhausted", retry_delay

        if retry_delay is not None and retry_delay > 120:
            return "quota_exhausted", retry_delay

        return "rate_limited", retry_delay

    if (
        code in (401, 403)
        or status in ("UNAUTHENTICATED", "PERMISSION_DENIED")
        or "api key not valid" in text
        or "api_key_invalid" in text
    ):
        return "auth", None

    if code == 404 or status == "NOT_FOUND":
        return "model_not_found", None

    if (
        code in (500, 502, 503, 504)
        or status in (
            "INTERNAL",
            "UNAVAILABLE",
            "DEADLINE_EXCEEDED"
        )
        or "overloaded" in text
    ):
        return "server_error", retry_delay

    module_name = type(error).__module__ or ""

    if (
        isinstance(error, (ConnectionError, TimeoutError))
        or module_name.startswith(_NETWORK_MODULES)
        or any(marker in text for marker in _NETWORK_MARKERS)
    ):
        return "network", None

    return None


def _format_duration(seconds):
    seconds = int(seconds)

    if seconds >= 3600:
        return (
            f"{seconds // 3600}h "
            f"{(seconds % 3600) // 60}m"
        )

    if seconds >= 60:
        return f"{seconds // 60}m"

    return f"{seconds}s"


def describe_gemini_reason(reason):

    descriptions = {
        "quota_exhausted":
            "Gemini's request quota is used up (daily limit reached).",

        "rate_limited":
            "Gemini is rate-limiting requests (too many per minute).",

        "server_error":
            "Gemini's servers are temporarily unavailable.",

        "network":
            "Could not reach Gemini (network problem).",

        "auth":
            "Gemini rejected the API key. Check GEMINI_API_KEY in .env.",

        "model_not_found":
            f"Gemini model '{GEMINI_MODEL}' was not found for this "
            f"API key. Check GEMINI_MODEL in .env.",

        "not_configured":
            "GEMINI_API_KEY is missing. Add it to the .env file.",

        "empty_response":
            "Gemini returned an empty response.",
    }

    return descriptions.get(
        reason,
        "Gemini is currently unavailable."
    )


_cooldown_lock = threading.Lock()
_cooldown_until = 0.0
_cooldown_reason = ""


def _start_cooldown(seconds, reason):
    global _cooldown_until, _cooldown_reason

    new_until = time.time() + seconds

    with _cooldown_lock:
        if new_until > _cooldown_until:
            _cooldown_until = new_until
            _cooldown_reason = reason


def get_gemini_cooldown():

    with _cooldown_lock:
        remaining = int(_cooldown_until - time.time())

        if remaining <= 0:
            return 0, ""

        return remaining, _cooldown_reason


def clear_gemini_cooldown():
    global _cooldown_until, _cooldown_reason

    with _cooldown_lock:
        _cooldown_until = 0.0
        _cooldown_reason = ""


def _raise_if_cooling_down():

    remaining, reason = get_gemini_cooldown()

    if remaining > 0:
        raise GeminiUnavailableError(
            reason,
            f"{describe_gemini_reason(reason)} "
            f"Gemini is paused for about "
            f"{_format_duration(remaining)} to avoid wasting requests.",
            retry_after=remaining
        )


# =====================================================
# 3. GEMINI CLIENT
# =====================================================


def get_gemini_client():

    api_key = os.getenv("GEMINI_API_KEY")

    # Streamlit Community Cloud stores credentials in st.secrets.
    if not api_key:
        try:
            import streamlit as st
            api_key = st.secrets.get("GEMINI_API_KEY")
        except Exception:
            api_key = None

    if not api_key:
        raise GeminiUnavailableError(
            "not_configured",
            describe_gemini_reason("not_configured")
        )

    return genai.Client(api_key=api_key)


# =====================================================
# 4. GEMINI API WITH SAFE RETRIES
# =====================================================


def generate_gemini_response(
    prompt,
    model=None,
    max_output_tokens=GEMINI_OUTPUT_TOKENS
):

    selected_model = model or GEMINI_MODEL

    for attempt in range(1, MAX_ATTEMPTS + 1):

        _raise_if_cooling_down()

        client = get_gemini_client()

        try:
            response = client.models.generate_content(
                model=selected_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=TEMPERATURE,
                    max_output_tokens=max_output_tokens
                )
            )

        except Exception as error:

            classified = classify_gemini_error(error)

            if classified is None:
                raise

            reason, retry_delay = classified

            if reason == "quota_exhausted":

                cooldown = (
                    retry_delay
                    if retry_delay and retry_delay >= 60
                    else QUOTA_COOLDOWN_SECONDS
                )

                _start_cooldown(cooldown, reason)

                message = describe_gemini_reason(reason)

                if retry_delay:
                    message += (
                        f" Google suggests retrying in about "
                        f"{_format_duration(retry_delay)}."
                    )

                raise GeminiUnavailableError(
                    reason,
                    message,
                    retry_after=retry_delay
                ) from error

            if reason in ("auth", "model_not_found"):
                raise GeminiUnavailableError(
                    reason,
                    describe_gemini_reason(reason)
                ) from error

            if (
                reason == "rate_limited"
                and retry_delay
                and retry_delay > 30
            ):
                _start_cooldown(retry_delay, reason)

                raise GeminiUnavailableError(
                    reason,
                    describe_gemini_reason(reason),
                    retry_after=retry_delay
                ) from error

            if attempt == MAX_ATTEMPTS:

                if reason == "rate_limited":
                    _start_cooldown(
                        RATE_LIMIT_COOLDOWN_SECONDS,
                        reason
                    )

                raise GeminiUnavailableError(
                    reason,
                    describe_gemini_reason(reason)
                ) from error

            if retry_delay and retry_delay <= 30:
                wait_time = retry_delay + 1
            else:
                wait_time = 2 ** attempt

            print(
                f"Gemini temporary error ({reason}). "
                f"Retrying in {wait_time:.0f} seconds "
                f"(attempt {attempt}/{MAX_ATTEMPTS})..."
            )

            time.sleep(wait_time)
            continue

        text = getattr(response, "text", None)

        if not text or not text.strip():
            raise GeminiUnavailableError(
                "empty_response",
                describe_gemini_reason("empty_response")
            )

        return text.strip()

    raise GeminiUnavailableError(
        "server_error",
        "Gemini request failed after retries."
    )


# =====================================================
# 5. TEXT SPLITTING
# =====================================================


def split_large_text(text, max_chars):

    if max_chars <= 0:
        raise ValueError(
            "max_chars must be greater than zero."
        )

    paragraphs = text.split("\n")

    pieces = []
    current = ""

    for paragraph in paragraphs:

        paragraph = paragraph.strip()

        if not paragraph:
            continue

        if len(paragraph) > max_chars:

            if current.strip():
                pieces.append(current)

            current = ""

            for start in range(0, len(paragraph), max_chars):
                pieces.append(
                    paragraph[start:start + max_chars]
                )

            continue

        if (
            current
            and len(current) + len(paragraph) + 1 > max_chars
        ):
            pieces.append(current)
            current = paragraph

        else:
            if current:
                current += "\n" + paragraph
            else:
                current = paragraph

    if current.strip():
        pieces.append(current)

    return pieces


# =====================================================
# 6. PAGE-AWARE DOCUMENT CHUNKS
# =====================================================


def _serialize_coordinate_tables(page):
    """
    Serialize coordinate-extracted tables and generate
    deterministic experimental result records.

    Numerical result records are generated directly from
    the extracted table cells, not by the language model.
    """

    import re

    page_number = page.get("page_number", 1)
    tables = page.get("coordinate_tables", [])

    if not tables:
        return []

    serialized_tables = []

    for table_number, table in enumerate(tables, start=1):

        header = table.get("header", [])
        metric_columns = table.get("metric_columns", [])
        rows = table.get("rows", [])

        # Preserve the actual caption extracted from the PDF.

        caption = str(
            table.get("caption", "")
        ).strip()

        caption_lower = caption.lower()

        # Use the actual printed table number when available.
        caption_number_match = re.search(
            r"\btable\s+(\d+)\b",
            caption,
            flags=re.IGNORECASE
        )

        actual_table_number = (
            int(caption_number_match.group(1))
            if caption_number_match
            else table_number
        )

        # Identify benchmark and task only when explicitly supported
        # by the table caption.

        dataset_name = "Not specified"
        task_name = "Not specified"

        if "squad 1.1" in caption_lower:
            dataset_name = "SQuAD 1.1"
            task_name = "Question Answering"

        elif "squad 2.0" in caption_lower:
            dataset_name = "SQuAD 2.0"
            task_name = "Question Answering"

        elif "swag" in caption_lower:
            dataset_name = "SWAG"
            task_name = "Commonsense Inference"

        elif "conll-2003" in caption_lower:
            dataset_name = "CoNLL-2003"
            task_name = "Named Entity Recognition"

        experiment_name = (
            caption
            if caption
            else f"Table {actual_table_number}"
        )

        # Identify Dev and Test column positions.
        dev_x = None
        test_x = None

        for item in header:

            label = item.get("text", "").strip().lower()

            center = (
                float(item.get("x0", 0))
                + float(item.get("x1", 0))
            ) / 2

            if label == "dev":
                dev_x = center

            elif label == "test":
                test_x = center

        # Build explicit metric column names.
        column_labels = []

        for column in metric_columns:

            metric_name = column.get("name", "").strip()
            center = float(column.get("center", 0))

            if dev_x is not None and test_x is not None:

                split_x = (dev_x + test_x) / 2

                group_name = (
                    "Dev" if center < split_x else "Test"
                )

                if metric_name.lower() in ("dev", "test"):
                    column_label = f"{group_name} Accuracy"
                else:
                    column_label = f"{group_name} {metric_name}"

            else:
                column_label = metric_name or "Metric"

            column_labels.append(column_label)

        lines = [
            f"[STRUCTURED TABLE EVIDENCE - PAGE {page_number}]",
            f"Table number on page: {actual_table_number}",
            "Column definitions: " + " | ".join(column_labels),
            "Values are aligned with the column definitions above.",
            "Not reported means the source table contains no reported value.",
            ""
        ]

        if caption:
            lines.append(f"Table caption: {caption}")

        lines.append(f"Dataset or benchmark: {dataset_name}")
        lines.append(f"Task: {task_name}")
        lines.append("")

        row_count = 0
        generated_records = 0
        current_section = "Not specified"

        for row in rows:

            row_type = row.get("type")

            if row_type == "section":

                section_name = row.get("name", "").strip()

                if section_name:
                    current_section = section_name
                    lines.append(f"Section: {section_name}")

                continue

            if row_type != "data":
                continue

            model_name = row.get("model", "").strip()
            values = row.get("values", [])

            if not model_name:
                continue

            lines.append(f"Model: {model_name}")

            for index, column_label in enumerate(column_labels):

                value = (
                    values[index]
                    if index < len(values)
                    else "Not reported"
                )

                value = str(value).strip()

                if not value:
                    value = "Not reported"

                lines.append(f"{column_label}: {value}")

                # Skip cells without a reported numerical value.
                if value.lower() in (
                    "not reported",
                    "not specified",
                    "-",
                    "--",
                    "n/a",
                    "na"
                ):
                    continue

                # Accept only a complete numerical value.
                if not re.fullmatch(
                    r"[-+]?\d+(?:\.\d+)?%?",
                    value
                ):
                    continue

                # Separate evaluation split and metric.
                label_match = re.match(
                    r"^(Dev|Test)\s+(.+)$",
                    column_label,
                    flags=re.IGNORECASE
                )

                if label_match:

                    evaluation_split = (
                        label_match.group(1).capitalize()
                    )

                    metric_label = (
                        label_match.group(2).strip()
                    )

                else:

                    evaluation_split = "Not specified"
                    metric_label = column_label.strip()

                # Normalize common metric names.
                metric_key = metric_label.lower()

                metric_mapping = {
                    "em": "Exact Match (EM)",
                    "exact match": "Exact Match (EM)",
                    "exact match (em)": "Exact Match (EM)",
                    "f1": "F1",
                    "accuracy": "Accuracy",
                    "precision": "Precision",
                    "recall": "Recall",
                    "bleu": "BLEU",
                    "rouge": "ROUGE",
                }

                metric_name = metric_mapping.get(
                    metric_key,
                    metric_label
                )

                supporting_evidence = (
                    f"Table caption: {caption or 'Not available'}; "
                    f"Section: {current_section}; "
                    f"{model_name}, "
                    f"{column_label}: {value}"
                )

                # Generate a complete protected record.
                # Numerical values remain exactly as extracted.
                record = [
                    "RESULT RECORD:",
                    f"- Experiment: {experiment_name}",
                    f"- Dataset or benchmark: {dataset_name}",
                    f"- Task: {task_name}",
                    f"- Model or configuration: {model_name}",
                    f"- Evaluation split: {evaluation_split}",
                    f"- Metric name: {metric_name}",
                    f"- Exact reported value: {value}",
                    "- Unit: Not specified",
                    "- Baseline or comparison: Not specified",
                    "- Reported improvement: Not specified",
                    f"- Page reference: Page {page_number}, Table {actual_table_number}",
                    f"- Supporting evidence: {supporting_evidence}",
                    "END RESULT RECORD"
                ]

                lines.extend(record)
                lines.append("")

                generated_records += 1

            lines.append("")
            row_count += 1

        if row_count:

            lines.append(f"Total data rows: {row_count}")

            lines.append(
                f"Total deterministic result records: {generated_records}"
            )

            lines.append(
                f"End of structured table evidence - PAGE {page_number}"
            )

            serialized_tables.append("\n".join(lines))

    return serialized_tables
def build_document_chunks(
    pages,
    max_chunk_chars=MAX_CHUNK_CHARS
):

    if max_chunk_chars <= 0:
        raise ValueError(
            "max_chunk_chars must be greater than zero."
        )

    chunks = []
    current_chunk = ""

    for page in pages:

        page_number = page.get("page_number", 1)
        page_text = page.get("text", "").strip()

        table_blocks = _serialize_coordinate_tables(page)

        if not page_text and not table_blocks:
            continue

        page_marker = f"[PAGE {page_number}]"

        content_limit = (
            max_chunk_chars - len(page_marker) - 1
        )

        if content_limit <= 0:
            raise ValueError(
                "max_chunk_chars is too small to preserve "
                "page references."
            )

        # Original PDF text is preserved and split normally.
        page_parts = (
            split_large_text(page_text, content_limit)
            if page_text
            else []
        )

        page_segments = []

        for part in page_parts:

            page_segments.append(
                f"{page_marker}\n{part.strip()}"
            )

                # Split structured tables only between complete model groups.
        for table_block in table_blocks:

            lines = table_block.splitlines()

            header_lines = []
            model_groups = []
            current_group = []

            for line in lines:

                if line.startswith("Model:"):

                    if current_group:
                        model_groups.append(current_group)

                    current_group = [line]

                elif current_group:
                    current_group.append(line)

                else:
                    header_lines.append(line)

            if current_group:
                model_groups.append(current_group)

            if not model_groups:
                raise ValueError(
                    f"Could not safely split structured table "
                    f"on page {page_number}."
                )

            current_groups = []

            for group in model_groups:

                candidate_groups = current_groups + [group]

                candidate_table = "\n".join(
                    header_lines
                    + [
                        line
                        for item in candidate_groups
                        for line in item
                    ]
                )

                candidate_content = (
                    f"{page_marker}\n{candidate_table}"
                )

                if len(candidate_content) <= max_chunk_chars:

                    current_groups.append(group)

                else:

                    if current_groups:

                        completed_table = "\n".join(
                            header_lines
                            + [
                                line
                                for item in current_groups
                                for line in item
                            ]
                        )

                        page_segments.append(
                            f"{page_marker}\n{completed_table}"
                        )

                    single_table = "\n".join(
                        header_lines + group
                    )

                    single_content = (
                        f"{page_marker}\n{single_table}"
                    )

                    if len(single_content) > max_chunk_chars:

                        raise ValueError(
                            f"A single model group on page "
                            f"{page_number} exceeds the chunk limit."
                        )

                    current_groups = [group]

            if current_groups:

                completed_table = "\n".join(
                    header_lines
                    + [
                        line
                        for item in current_groups
                        for line in item
                    ]
                )

                page_segments.append(
                    f"{page_marker}\n{completed_table}"
                )
        for page_content in page_segments:

            if len(page_content) > max_chunk_chars:
                raise ValueError(
                    f"Page {page_number} segment exceeds "
                    f"the {max_chunk_chars}-character limit."
                )

            separator = "\n" if current_chunk else ""

            candidate = (
                current_chunk
                + separator
                + page_content
            )

            if len(candidate) > max_chunk_chars:

                if current_chunk:
                    chunks.append(current_chunk)

                current_chunk = page_content

            else:
                current_chunk = candidate

    if current_chunk:
        chunks.append(current_chunk)

    for index, chunk in enumerate(chunks, start=1):

        if len(chunk) > max_chunk_chars:
            raise ValueError(
                f"Chunk {index} has {len(chunk)} characters; "
                f"maximum allowed is {max_chunk_chars}."
            )

    return chunks


# =====================================================
# 7. PAPER METADATA
# =====================================================


def build_metadata_context(paper_data):

    metadata = paper_data.get("metadata", {})

    if not isinstance(metadata, dict):
        return ""

    fields = [
        ("Title", metadata.get("title")),
        ("Authors", metadata.get("authors")),
        ("Author", metadata.get("author")),
        ("Publication", metadata.get("publication")),
        ("Journal", metadata.get("journal")),
        ("DOI", metadata.get("doi")),
        ("Source URL", paper_data.get("source_url"))
    ]

    lines = []

    for label, value in fields:
        if value:
            lines.append(f"{label}: {value}")

    if not lines:
        return ""

    return (
        "EXTRACTED DOCUMENT METADATA\n"
        + "\n".join(lines)
        + "\n\n"
        "Metadata is supporting information. "
        "If it conflicts with the paper's actual title "
        "page, identify the conflict instead of guessing.\n"
    )


# =====================================================
# 8. FINAL GEMINI RESEARCH REPORT PROMPT
# =====================================================


def create_final_summary(
    source_content,
    model=None,
    metadata_context=""
):

    prompt = f"""
You are a rigorous academic research analyst.

Your job is to produce an accurate, detailed,
beginner-friendly analysis of a scientific research paper.

Use only the supplied evidence.

{metadata_context}

ACADEMIC ACCURACY RULES:

1. Never invent authors, titles, datasets, sample sizes,
   experimental configurations, numerical results,
   equations, limitations or future research.

2. Preserve numerical results EXACTLY.

3. Keep different datasets and experimental settings separate.

4. Preserve units, metric names and model configurations.

5. Attach page references when available.

6. Never invent page references.

7. Separate:
   A. Explicit author statements.
   B. Experimental findings.
   C. Your own analytical interpretations.

8. Never present an interpretation as an author statement.

9. Do not describe established techniques as novel.

10. Missing information in the supplied extract does not
    prove that the original paper lacks that information.

11. If information is unavailable, write:
    "Not specified in the available paper content."

12. If evidence conflicts, explain the conflict.

REQUIRED REPORT STRUCTURE:

# 1. Paper Overview

Include:
- Exact title.
- Authors.
- Publication details.
- Research field.
- Main subject.
- Purpose of the paper.

# 2. Research Problem

Explain:
- Problem investigated.
- Why it matters.
- Previous approaches.
- Their weaknesses.
- Problem addressed by the paper.

# 3. Research Objectives

List explicitly stated or clearly supported objectives.
Separate explicit objectives from inferred objectives.

# 4. Research Methodology

Explain:
- Research design.
- Proposed model.
- Architecture and components.
- Algorithms and mathematical methods.
- Step-by-step process.
- Datasets.
- Experimental setup.
- Training configuration.
- Hardware.
- Evaluation metrics.

# 5. Main Contributions and Novelty

Identify:
- Contributions claimed by authors.
- Actual technical contributions.
- Differences from previous approaches.
- New architectural elements.
- Contributions supported by experiments.

# 6. Experimental Results and Findings

Include:
- Dataset-specific results.
- Exact numerical scores.
- Evaluation metrics.
- Baseline comparisons.
- Ablation studies.
- Training time and hardware.
- Important observations.

For every important numerical result, include:
- Exact value.
- Dataset or task.
- Model configuration.
- Page reference, if available.

Never mix results from different experiments.

# 7. Research Gap and Original Contribution Analysis

Separate:
A. Gap identified by the authors.
B. How this paper addresses the gap.
C. Your own evidence-based assessment of unresolved issues.

# 8. Limitations

Separate:

## Explicitly stated limitations

Only limitations acknowledged by the authors.

## Evidence-based potential limitations

Your own analytical observations, clearly labelled.

# 9. Future Research Directions

Include only future directions explicitly mentioned by the authors.

If none are identified in the supplied content, say so.

# 10. Important Technical Concepts

Explain:
- Models and architectures.
- Algorithms.
- Mathematical equations.
- Parameters.
- Evaluation metrics.
- Important terminology.

Preserve the meaning of equations.

# 11. Overall Takeaway

Summarize:
- Problem.
- Proposed approach.
- Experimental findings.
- Most important results.
- Research significance.

# 12. Evidence Gaps

Identify:
- Missing evidence.
- Why it matters.
- Whether the gap is in the supplied extract
  or explicitly acknowledged by the authors.

FINAL SELF-CHECK:

Before answering, verify:
1. Title and author names.
2. Numerical results.
3. Dataset associations.
4. Experimental settings.
5. Limitations.
6. Future research claims.
7. Novelty claims.
8. Page references.
9. Mathematical explanations.

Correct inconsistencies where the evidence permits.

RESEARCH PAPER EVIDENCE:

{source_content}

Generate the complete report now.
"""

    return generate_gemini_response(
        prompt,
        model=model,
        max_output_tokens=GEMINI_OUTPUT_TOKENS
    )


# =====================================================
# 9. FINAL SUMMARY VERIFICATION
# =====================================================


def verify_final_summary(
    original_paper_text,
    draft_summary,
    model=None
):

    if not original_paper_text or not original_paper_text.strip():
        raise ValueError(
            "Original paper text is required for verification."
        )

    if not draft_summary or not draft_summary.strip():
        raise ValueError(
            "A draft summary is required for verification."
        )

    prompt = f"""
You are the evidence-verification stage of ResearchMind AI.

Your task is to audit and correct the DRAFT REPORT using the
ORIGINAL EXTRACTED PAPER TEXT as the only factual source.

VERIFICATION RULES:
1. Check every title, author, date, dataset, method, number, metric,
   comparison, equation explanation, limitation and future-work claim.
2. Correct numerical values only when the original text clearly supports
   the correction. Preserve decimals, units, task names and model settings.
3. Keep results from different datasets and experiments separate.
4. Remove claims that are unsupported by the original text. If a useful
   analytical interpretation is retained, label it clearly as interpretation.
5. Do not invent author-stated limitations or future work.
6. Do not say information is absent from the complete paper merely because
   it is not visible in the supplied extracted text. Use “Not established
   from the extracted text” where appropriate.
7. Page references must match explicit [PAGE n] markers in the source.
   Never guess page numbers.
8. Do not add facts from your general knowledge or the internet.
9. Preserve the report's existing 12-section structure and beginner-friendly
   explanations. Do not shorten it unnecessarily.
10. If the source itself is ambiguous or conflicting, report the conflict
    instead of guessing.

OUTPUT REQUIREMENT:
Return the corrected complete report in Markdown only. Do not include an
introductory note about the verification process or claim that every fact
is guaranteed correct.

================ ORIGINAL EXTRACTED PAPER TEXT ================
{original_paper_text}

================ DRAFT REPORT TO AUDIT ================
{draft_summary}

Return the corrected report now.
"""

    verified = generate_gemini_response(
        prompt,
        model=model,
        max_output_tokens=GEMINI_OUTPUT_TOKENS
    )

    if not verified or not verified.strip():
        raise GeminiUnavailableError(
            "empty_response",
            "Gemini returned an empty verified report."
        )

    return verified.strip()


def _verify_or_keep_draft(full_text, draft_summary, model):

    if not VERIFY_SUMMARY:
        print(
            "ResearchMind: Verification disabled "
            "(GEMINI_VERIFY_SUMMARY=false)."
        )
        return draft_summary

    print(
        "ResearchMind: Verifying report against original paper text."
    )

    try:
        verified = verify_final_summary(
            original_paper_text=full_text,
            draft_summary=draft_summary,
            model=model
        )

    except GeminiUnavailableError as error:
        print(
            f"ResearchMind: Verification skipped: {error}"
        )
        return draft_summary + VERIFICATION_SKIPPED_NOTE

    print("ResearchMind: Evidence verification completed.")

    return verified


# =====================================================
# 10. CHUNK-LEVEL EVIDENCE EXTRACTION
# =====================================================


def summarize_chunk(
    chunk,
    chunk_number,
    total_chunks,
    model=None
):

    prompt = f"""
You are an academic research evidence extractor.

Analyze chunk {chunk_number} of {total_chunks}
from a scientific research paper.

This is only part of the paper.
Do not assume that this chunk represents the entire paper.

Extract detailed, structured evidence that can be
combined with evidence from the other chunks.

====================================================
EXTRACT THE FOLLOWING
====================================================

1. PAPER IDENTITY
- Exact title, if present.
- Authors, if present.
- Publication details.
- Research field.

2. RESEARCH PROBLEM
- Problem investigated.
- Motivation.
- Previous approaches discussed.
- Weaknesses explicitly identified.

3. OBJECTIVES
- Explicit objectives.
- Purpose of the work.

4. METHODOLOGY
- Research design.
- Model architecture.
- Algorithms.
- Procedures.
- Implementation details.

5. DATASETS AND EXPERIMENTAL SETUP
- Dataset names.
- Dataset sizes.
- Training and testing splits.
- Hardware.
- Training configuration.
- Evaluation metrics.

6. TECHNICAL DETAILS
- Important concepts.
- Equations.
- Parameters.
- Model components.
- Definitions.

7. EXPERIMENTAL RESULTS
- Exact numerical values.
- Metric names.
- Dataset and task associated with each value.
- Baseline comparisons.
- Ablation results.
- Experimental observations.

8. CONTRIBUTIONS
- Contributions claimed by the authors.
- Technical innovations supported by this section.

9. LIMITATIONS
- Limitations explicitly acknowledged.
- Potential weaknesses directly supported by evidence.

10. FUTURE RESEARCH
- Future work explicitly mentioned.

11. RESEARCH GAP
- Problems addressed.
- Unresolved issues supported by this section.

====================================================
IMPORTANT EVIDENCE RULES
====================================================

- Use only this chunk.
- Preserve page references.
- Preserve exact numbers, decimals and units.
- Never change a reported metric.
- Keep different experimental settings separate.
- Preserve equations and important variables.
- Do not invent missing details.
- Do not describe established methods as novel.
- Distinguish author claims from your interpretation.
- Do not infer that missing information is absent
  from the complete paper.
- Do not invent limitations or future work.
- Avoid repetitive descriptions.

For important numerical findings, use this format:

Finding:
Exact value:
Dataset/task:
Experimental setting:
Page:
Evidence or explanation:

If information is unavailable, write:
"Not specified in this section."

Return structured evidence, not a final report.

PAPER CONTENT:

{chunk}
"""

    return generate_gemini_response(
        prompt,
        model=model,
        max_output_tokens=CHUNK_OUTPUT_TOKENS
    )


# =====================================================
# 11. GEMINI SUMMARIZATION PIPELINE
# =====================================================


def _collect_full_text(paper_data):

    pages = paper_data.get("pages", [])

    if not pages:
        raise ValueError(
            "No readable pages were found in the document."
        )

    full_text_parts = []

    for page in pages:

        page_number = page.get("page_number", 1)
        page_text = page.get("text", "").strip()

        if page_text:
            full_text_parts.append(
                f"\n[PAGE {page_number}]\n{page_text}"
            )

    full_text = "\n\n".join(full_text_parts)

    if not full_text.strip():
        raise ValueError(
            "No readable text was extracted from the document."
        )

    return pages, full_text


def _summarize_with_gemini(
    paper_data,
    model=None,
    progress_callback=None
):

    start_time = time.perf_counter()

    pages, full_text = _collect_full_text(paper_data)
    metadata_context = build_metadata_context(paper_data)
    total_chars = len(full_text)

    print("\nResearchMind: Starting Gemini summarization.")
    print(f"Extracted characters: {total_chars:,}")

    if total_chars <= MAX_DIRECT_CHARS:

        print(
            "ResearchMind: Using one-pass summarization."
        )

        if progress_callback:
            progress_callback(0.2)

        final_summary = create_final_summary(
            full_text,
            model=model,
            metadata_context=metadata_context
        )

        if progress_callback:
            progress_callback(0.75)

        final_summary = _verify_or_keep_draft(
            full_text,
            final_summary,
            model
        )

        if progress_callback:
            progress_callback(1.0)

        elapsed = time.perf_counter() - start_time

        print(
            f"ResearchMind: One-pass completed "
            f"in {elapsed:.2f} seconds."
        )

        return final_summary

    print(
        "ResearchMind: Using parallel chunk summarization."
    )

    chunks = build_document_chunks(
        pages,
        MAX_CHUNK_CHARS
    )

    if not chunks:
        raise ValueError(
            "Unable to create document chunks."
        )

    print(
        f"ResearchMind: Total chunks: {len(chunks)}"
    )

    chunk_summaries = [None] * len(chunks)
    completed = 0

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        future_to_index = {
            executor.submit(
                summarize_chunk,
                chunk,
                index + 1,
                len(chunks),
                model
            ): index
            for index, chunk in enumerate(chunks)
        }

        try:
            for future in as_completed(future_to_index):

                index = future_to_index[future]

                chunk_summaries[index] = future.result()
                completed += 1

                print(
                    f"ResearchMind: Completed "
                    f"{completed}/{len(chunks)} chunks."
                )

                if progress_callback:
                    progress_callback(
                        0.75 * completed / len(chunks)
                    )

        except BaseException:

            for pending in future_to_index:
                pending.cancel()

            raise

    if any(item is None for item in chunk_summaries):
        raise RuntimeError(
            "Some document chunks were not processed."
        )

    combined_evidence = "\n\n".join(
        f"===== CHUNK {index + 1} EVIDENCE =====\n{summary}"
        for index, summary in enumerate(chunk_summaries)
    )

    if progress_callback:
        progress_callback(0.85)

    print(
        "ResearchMind: Generating final research report."
    )

    final_summary = create_final_summary(
        combined_evidence,
        model=model,
        metadata_context=metadata_context
    )

    if progress_callback:
        progress_callback(0.9)

    final_summary = _verify_or_keep_draft(
        full_text,
        final_summary,
        model
    )

    if progress_callback:
        progress_callback(1.0)

    elapsed = time.perf_counter() - start_time

    print(
        f"ResearchMind: Gemini summary completed "
        f"in {elapsed:.2f} seconds."
    )

    return final_summary


# =====================================================
# 12. QWEN LOCAL MODEL SUMMARIZATION
# =====================================================


def _ask_qwen(
    prompt,
    model=None,
    num_predict=None
):

    response = chat_with_ollama(
        prompt,
        model=model or QWEN_MODEL,
        num_ctx=QWEN_NUM_CTX,
        num_predict=num_predict
    )

    if not response or not str(response).strip():
        raise OllamaError(
            "Qwen returned an empty response."
        )

    return str(response).strip()


def _combine_evidence(items):

    return "\n\n".join(
        f"===== EVIDENCE PART {index + 1} =====\n{item}"
        for index, item in enumerate(items)
    )


# =====================================================
# 12A. PAGE-PRESERVING EVIDENCE SPLITTER
# =====================================================


def _split_evidence_preserving_pages(
    evidence,
    max_chars=10000
):
    """
    Split evidence into bounded pieces while preserving:
    - Every original character
    - Page order
    - Page references on every piece
    - No duplication or truncation
    """

    if max_chars <= 0:
        raise ValueError(
            "max_chars must be greater than zero."
        )

    if not evidence:
        return []

    page_pattern = re.compile(
        r"(?m)^\[PAGE\s+([^\]]+)\]\s*$"
    )

    matches = list(page_pattern.finditer(evidence))

    if not matches:
        # No page markers: use ordinary lossless splitting.
        pieces = []
        start = 0

        while start < len(evidence):
            end = min(start + max_chars, len(evidence))

            if end < len(evidence):
                newline = evidence.rfind("\n", start, end)
                space = evidence.rfind(" ", start, end)

                boundary = max(newline, space)

                if boundary > start:
                    end = boundary + 1

            pieces.append(evidence[start:end])
            start = end

        return pieces

    pieces = []

    for index, match in enumerate(matches):

        page_number = match.group(1)

        content_start = match.end()

        if content_start < len(evidence):
            if evidence[content_start] == "\n":
                content_start += 1

        content_end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(evidence)
        )

        page_content = evidence[
            content_start:content_end
        ]

        marker = f"[PAGE {page_number}]\n"

        available_chars = max_chars - len(marker)

        if available_chars <= 0:
            raise OllamaError(
                "Character limit is too small to preserve "
                "the page marker."
            )

        if not page_content:
            pieces.append(marker)
            continue

        start = 0

        while start < len(page_content):

            end = min(
                start + available_chars,
                len(page_content)
            )

            if end < len(page_content):

                newline = page_content.rfind(
                    "\n", start, end
                )

                space = page_content.rfind(
                    " ", start, end
                )

                boundary = max(newline, space)

                if boundary > start:
                    end = boundary + 1

            if end <= start:
                end = min(
                    start + available_chars,
                    len(page_content)
                )

            piece = marker + page_content[start:end]

            pieces.append(piece)

            start = end

    # Verify that all original page content is preserved.
    reconstructed = []

    for piece in pieces:
        header, separator, content = piece.partition("\n")

        if not separator:
            raise OllamaError(
                "Generated evidence piece has no page separator."
            )

        reconstructed.append(content)

    original_pages = []

    for index, match in enumerate(matches):

        content_start = match.end()

        if (
            content_start < len(evidence)
            and evidence[content_start] == "\n"
        ):
            content_start += 1

        content_end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(evidence)
        )

        original_pages.append(
            evidence[content_start:content_end]
        )

    reconstructed_pages = {}

    for piece in pieces:

        header, _, content = piece.partition("\n")

        page_number = header[len("[PAGE "):-1]

        reconstructed_pages.setdefault(
            page_number, []
        ).append(content)

    for index, match in enumerate(matches):

        page_number = match.group(1)

        actual = "".join(
            reconstructed_pages.get(page_number, [])
        )

        expected = original_pages[index]

        if actual != expected:
            raise OllamaError(
                f"Evidence changed during splitting "
                f"for page {page_number}."
            )

    if any(len(piece) > max_chars for piece in pieces):
        raise OllamaError(
            "Evidence splitter produced an oversized piece."
        )

    return pieces


# =====================================================
# 12B. ADAPTIVE QWEN EXTRACTION
# =====================================================


def _extract_qwen_chunk_adaptive(
    prompt,
    chunk_text,
    model=None,
    num_predict=None,
    depth=0,
    max_depth=3
):
    """
    Extract evidence from a document chunk.

    If Qwen reaches its output-token limit, split only the
    failing chunk and retry its smaller pieces.
    """

    try:
        return _ask_qwen(
            prompt,
            model=model,
            num_predict=num_predict
        )

    except OllamaError as error:

        error_message = str(error).lower()

        output_limit_error = (
            "output limit" in error_message
            or "num_predict" in error_message
        )

        if not output_limit_error:
            raise

        if depth >= max_depth:
            raise OllamaError(
                "Qwen extraction still exceeded its output "
                f"limit after {max_depth} adaptive splits. "
                "The document section needs a shorter extraction "
                "prompt or a smaller evidence scope."
            ) from error

        current_limit = max(1000, len(chunk_text) // 2)

        if current_limit >= len(chunk_text):
            raise

        smaller_chunks = _split_evidence_preserving_pages(
            chunk_text,
            max_chars=current_limit
        )

        if len(smaller_chunks) < 2:
            raise OllamaError(
                "Unable to split the oversized Qwen chunk "
                "into smaller pieces."
            ) from error

        print(
            "ResearchMind: Qwen output limit reached. "
            f"Splitting failed chunk into {len(smaller_chunks)} "
            f"smaller pieces (depth {depth + 1})."
        )

        extracted_parts = []

        for part_index, smaller_chunk in enumerate(
            smaller_chunks,
            start=1
        ):

            smaller_prompt = prompt.replace(
                chunk_text,
                smaller_chunk,
                1
            )

            print(
                "ResearchMind: Retrying smaller piece "
                f"{part_index}/{len(smaller_chunks)}."
            )

            extracted_parts.append(
                _extract_qwen_chunk_adaptive(
                    smaller_prompt,
                    smaller_chunk,
                    model=model,
                    num_predict=num_predict,
                    depth=depth + 1,
                    max_depth=max_depth
                )
            )

        return _combine_evidence(extracted_parts)


# =====================================================
# 12C. PROTECTED EXPERIMENTAL RESULT RECORDS
# =====================================================


def _extract_protected_result_records(evidence_items):

    required_fields = [
        "Experiment",
        "Dataset or benchmark",
        "Task",
        "Model or configuration",
        "Evaluation split",
        "Metric name",
        "Exact reported value",
        "Unit",
        "Baseline or comparison",
        "Reported improvement",
        "Page reference",
        "Supporting evidence",
    ]

    field_pattern = re.compile(
        r"(?m)^-\s*("
        + "|".join(
            re.escape(field)
            for field in required_fields
        )
        + r")\s*:"
    )

    record_start_pattern = re.compile(
        r"(?m)^RESULT RECORD:\s*$"
    )

    record_end_pattern = re.compile(
        r"(?m)^END RESULT RECORD\s*$"
    )

    protected_records = []
    remaining_items = []

    for item in evidence_items:

        text = str(item)

        starts = list(record_start_pattern.finditer(text))
        ends = list(record_end_pattern.finditer(text))

        if not starts and not ends:
            remaining_items.append(text)
            continue

        # An orphan ending marker is retained as ordinary evidence.
        if not starts and ends:
            print(
                "ResearchMind: Found an ending marker without "
                "a starting marker. Preserving the evidence item."
            )
            remaining_items.append(text)
            continue

        if len(starts) != len(ends):
            raise OllamaError(
                "Unmatched RESULT RECORD start/end marker. "
                "Original evidence was not discarded."
            )

        cursor = 0

        for start, end in zip(starts, ends):

            if start.start() < cursor or end.start() < start.end():
                raise OllamaError(
                    "Invalid RESULT RECORD marker order. "
                    "Original evidence was not discarded."
                )

            prefix = text[cursor:start.start()]

            if prefix.strip():
                remaining_items.append(prefix.strip())

            record_text = text[start.start():end.end()].strip()

            found_fields = field_pattern.findall(record_text)

            missing_fields = [
                field
                for field in required_fields
                if field not in found_fields
            ]

            duplicate_fields = [
                field
                for field in required_fields
                if found_fields.count(field) > 1
            ]

            if missing_fields or duplicate_fields:
                raise OllamaError(
                    "Incomplete or malformed RESULT RECORD. "
                    f"Missing fields: {missing_fields}. "
                    f"Duplicate fields: {duplicate_fields}. "
                    "Original evidence was not discarded."
                )

            protected_records.append(record_text)
            cursor = end.end()

        suffix = text[cursor:]

        if suffix.strip():
            remaining_items.append(suffix.strip())

    return remaining_items, protected_records


def _protect_result_records_with_placeholders(evidence_items):
    """
    Protect complete, valid experimental result records.

    Handles records spanning multiple evidence items.
    Incomplete or malformed records remain ordinary evidence.
    No original evidence is silently discarded.
    """

    marker_pattern = re.compile(
    r"(?m)^RESULT RECORD:[ \t]*$"
    r"|^END RESULT RECORD[ \t]*$"
)

    combined_text = "\n\n".join(
        str(item) for item in evidence_items
    )

    markers = list(marker_pattern.finditer(combined_text))

    if not markers:
        return list(evidence_items), []

    protected_records = []
    parts = []
    cursor = 0
    pending_start = None

    for marker in markers:

        marker_text = marker.group()

        is_start = marker_text.startswith("RESULT RECORD:")

        if is_start:

            if pending_start is None:

                parts.append(
                    combined_text[cursor:marker.start()]
                )

                pending_start = marker
                cursor = marker.start()

            else:
                # Previous record had no ending marker.
                # Preserve it unchanged and start a new candidate.
                parts.append(
                    combined_text[cursor:marker.start()]
                )

                pending_start = marker
                cursor = marker.start()

            continue

        # This is an ending marker.

        if pending_start is None:
            # Orphan ending marker: preserve it unchanged.
            continue

        record_text = combined_text[
            pending_start.start():marker.end()
        ].strip()

        try:
            _, validated_records = (
                _extract_protected_result_records(
                    [record_text]
                )
            )

            valid_record = len(validated_records) == 1

        except OllamaError:
            valid_record = False

        if valid_record:

            placeholder = (
                f"[[PROTECTED_RESULT_RECORD_"
                f"{len(protected_records) + 1:04d}]]"
            )

            parts.append(placeholder)
            protected_records.append(record_text)

        else:
            # Keep incomplete or malformed records as evidence.
            parts.append(record_text)

            print(
                "ResearchMind: An incomplete or malformed "
                "result record was preserved without protection."
            )

        cursor = marker.end()
        pending_start = None

    # Preserve everything remaining, including an unmatched start.
    parts.append(combined_text[cursor:])

    protected_text = "".join(parts)

    print(
        f"ResearchMind: Protected "
        f"{len(protected_records)} complete experimental result records."
    )

    return [protected_text], protected_records


def _restore_protected_result_records(
    compressed_evidence,
    protected_records
):

    restored = str(compressed_evidence)

    for index, record in enumerate(protected_records, start=1):

        placeholder = (
            f"[[PROTECTED_RESULT_RECORD_{index:04d}]]"
        )

        occurrences = restored.count(placeholder)

        if occurrences != 1:
            raise OllamaError(
                "Protected result record placeholder was "
                f"missing or duplicated: {placeholder}. "
                "Original result records were not discarded."
            )

        restored = restored.replace(
            placeholder,
            record,
            1
        )

    remaining = re.findall(
        r"\[\[PROTECTED_RESULT_RECORD_[^\]]*\]\]",
        restored
    )

    if remaining:
        raise OllamaError(
            "Unexpected protected result record placeholders "
            f"remain after restoration: {remaining}"
        )

    return restored


def _validate_protected_placeholders(
    source_text,
    compressed_text
):

    pattern = re.compile(
        r"\[\[PROTECTED_RESULT_RECORD_\d{4}\]\]"
    )

    expected = pattern.findall(source_text)
    actual = pattern.findall(compressed_text)

    if expected != actual:
        raise OllamaError(
            "Protected placeholder validation failed. "
            f"Expected placeholders: {expected!r}. "
            f"Actual placeholders: {actual!r}. "
            f"Source count: {len(expected)}. "
            f"Response count: {len(actual)}. "
            "Original result records remain preserved."
        )

    return True


# =====================================================
# 12D. QWEN EVIDENCE COMPRESSION
# =====================================================


def _fit_evidence_for_qwen(
    evidence_items,
    model=None,
    limit_chars=QWEN_FINAL_EVIDENCE_CHARS
):
    """
    Select complete evidence paragraphs using category-balanced budgets.

    No Qwen calls are made during evidence preparation.
    Original evidence items remain unchanged.
    """

    if limit_chars <= 0:
        raise ValueError(
            "QWEN_FINAL_EVIDENCE_CHARS must be greater than zero."
        )

    items = [
        str(item).strip()
        for item in evidence_items
        if item and str(item).strip()
    ]

    if not items:
        raise OllamaError(
            "No evidence was available for the final report."
        )

    items, protected_records = (
        _protect_result_records_with_placeholders(items)
    )

    categories = [
        ("results", 18, r"experimental results?|quantitative results?|"
         r"findings|performance|outcome|accuracy|f1 score|exact match"),
        ("methodology", 14, r"methodology|proposed method|algorithm|"
         r"architecture|approach|experimental procedure"),
        ("datasets", 12, r"dataset|benchmark|corpus|training set|"
         r"test set|validation set|evaluation set"),
        ("training", 12, r"training configuration|hyperparameter|"
         r"learning rate|batch size|optimizer|training steps|epochs|"
         r"pretraining|fine.?tuning|masking strategy"),
        ("contributions", 10, r"contribution|novelty|research objective|"
         r"research objectives|main objective"),
        ("limitations", 10, r"limitation|future work|future direction|"
         r"research gap|weakness"),
        ("technical", 8, r"equation|mathematical|technical details|"
         r"implementation|parameter|token|model size"),
        ("problem", 8, r"research problem|motivation|background|"
         r"introduction|hypothesis"),
        ("other", 8, r"(?!)"),
    ]

    candidates = []
    sequence = 0

    for item_index, item in enumerate(items, start=1):

        # Keep protected result placeholders as independent candidates,
        # even when the source separates them with single newlines.
        item = re.sub(
            r"(\[\[PROTECTED_RESULT_RECORD_\d{4}\]\])",
            r"\n\n\1\n\n",
            item
        )

        paragraphs = [
            part.strip()
            for part in re.split(r"\n\s*\n", item)
            if part.strip()
        ]

        for paragraph in paragraphs:

            sequence += 1
            lower = paragraph.lower()

            score = 10

            if re.search(r"\d", paragraph):
                score += 15

            if re.search(
                r"\[\[PROTECTED_RESULT_RECORD_\d{4}\]\]",
                paragraph
            ):
                score += 10000

            if re.search(r"\bpage\s*\d+|\bp\.\s*\d+", lower):
                score += 5

            category_name = "other"

            for name, percentage, pattern in categories:
                if name != "other" and re.search(pattern, lower):
                    category_name = name
                    break

            block = (
                f"===== EVIDENCE PART {item_index} =====\n"
                f"{paragraph}"
            )

            candidates.append({
                "sequence": sequence,
                "category": category_name,
                "score": score,
                "block": block,
                "size": len(block) + 2,
            })

    selected = []
    selected_sequences = set()
    used_chars = 0

    # First pass: reserve a portion of the budget for each category.
    for category_name, percentage, pattern in categories:

        category_budget = int(
            limit_chars * percentage / 100
        )
        category_used = 0

        category_candidates = [
            candidate for candidate in candidates
            if candidate["category"] == category_name
        ]

        category_candidates.sort(
            key=lambda candidate: (
                -candidate["score"],
                candidate["sequence"]
            )
        )

        for candidate in category_candidates:

            if candidate["size"] > limit_chars - used_chars:
                continue

            if category_used + candidate["size"] > category_budget:
                continue

            selected.append(candidate)
            selected_sequences.add(candidate["sequence"])

            category_used += candidate["size"]
            used_chars += candidate["size"]

    # Second pass: use all remaining space for the strongest
    # complete paragraphs that did not fit their category budget.
    remaining_candidates = [
        candidate for candidate in candidates
        if candidate["sequence"] not in selected_sequences
    ]

    remaining_candidates.sort(
        key=lambda candidate: (
            -candidate["score"],
            candidate["sequence"]
        )
    )

    for candidate in remaining_candidates:

        if candidate["size"] <= limit_chars - used_chars:
            selected.append(candidate)
            selected_sequences.add(candidate["sequence"])
            used_chars += candidate["size"]

    selected.sort(key=lambda candidate: candidate["sequence"])

    if not selected:
        raise OllamaError(
            "No complete evidence paragraphs fit the configured "
            f"narrative budget of {limit_chars:,} characters. "
            "No evidence was truncated."
        )

    combined = "\n\n".join(
        candidate["block"] for candidate in selected
    )

    combined = _restore_protected_result_records(
        combined,
        protected_records
    )

    if len(combined) > limit_chars:
        raise OllamaError(
            "Selected evidence exceeds the configured narrative budget. "
            "No evidence was truncated."
        )

    category_counts = {}
    for candidate in selected:
        name = candidate["category"]
        category_counts[name] = category_counts.get(name, 0) + 1

    print(
        "ResearchMind: Category-balanced evidence selection completed."
    )
    print(
        f"ResearchMind: Selected {len(selected)} of "
        f"{len(candidates)} evidence paragraphs."
    )
    print(
        f"ResearchMind: Excluded "
        f"{len(candidates) - len(selected)} paragraphs."
    )
    print(
        f"ResearchMind: Selected evidence size: "
        f"{len(combined):,}/{limit_chars:,} characters."
    )
    print(
        "ResearchMind: Evidence category coverage: "
        + ", ".join(
            f"{name}={count}"
            for name, count in category_counts.items()
        )
    )
    print(
        f"ResearchMind: Protected result records in narrative: "
        f"{len(protected_records)}."
    )

    return combined


# =====================================================
# 12E. QWEN SUMMARIZATION PIPELINE
# =====================================================


def summarize_with_qwen(
    paper_data,
    progress_callback=None,
    model=None
):

    start_time = time.perf_counter()

    pages, full_text = _collect_full_text(paper_data)
    metadata_context = build_metadata_context(paper_data)

    is_encyclopedia = (
        paper_data.get("document_kind") == "encyclopedia"
    )

    chunks = build_document_chunks(
        pages,
        QWEN_CHUNK_CHARS
    )

    if not chunks:
        raise ValueError(
            "Unable to create document chunks."
        )

    # Preserve deterministic PDF table results separately
    # from Qwen-generated narrative summaries.
    _, deterministic_result_records = (
        _extract_protected_result_records(chunks)
    )

    print(
        "ResearchMind: Preserved "
        f"{len(deterministic_result_records)} "
        "deterministic experimental result records."
    )

    def get_record_field(record, field_name):
        match = re.search(
            r"(?m)^-\s*"
            + re.escape(field_name)
            + r"\s*:\s*(.*?)\s*$",
            record
        )
        return match.group(1).strip() if match else "Not specified"

    result_table_lines = [
        "AUTHORITATIVE DETERMINISTIC TABLE RESULTS",
        "",
        "These values were extracted directly from PDF table cells.",
        "Do not modify, recalculate, or invent values.",
        "",
        "| Experiment | Dataset | Task | Model | Split | Metric | Exact Value | Unit | Baseline | Improvement | Page |",
        "|---|---|---|---|---|---|---|---|---|---|---|"
    ]

    for record in deterministic_result_records:

        experiment = get_record_field(record, "Experiment")
        dataset = get_record_field(record, "Dataset or benchmark")
        task = get_record_field(record, "Task")
        model_name = get_record_field(
            record, "Model or configuration"
        )
        evaluation_split = get_record_field(
            record, "Evaluation split"
        )
        metric_name = get_record_field(record, "Metric name")
        exact_value = get_record_field(
            record, "Exact reported value"
        )
        unit = get_record_field(record, "Unit")
        baseline = get_record_field(
            record, "Baseline or comparison"
        )
        improvement = get_record_field(
            record, "Reported improvement"
        )
        page_reference = get_record_field(
            record, "Page reference"
        )

        row_values = [
            experiment,
            dataset,
            task,
            model_name,
            evaluation_split,
            metric_name,
            exact_value,
            unit,
            baseline,
            improvement,
            page_reference
        ]

        row_values = [
            str(value).replace("|", "\\|").replace("\n", " ").strip()
            for value in row_values
        ]

        result_table_lines.append(
            "| " + " | ".join(row_values) + " |"
        )

    compact_result_evidence = "\n".join(result_table_lines)

    print(
        "ResearchMind: Compact result table characters:",
        len(compact_result_evidence)
    )

    print(
        f"ResearchMind: Qwen processing {len(chunks)} chunks."
    )

    # FAST PATH: use the original extracted paper evidence directly.
    # Avoid 26 sequential Qwen extraction requests.
    # Deterministic result records are preserved separately below.

    # HTML articles retain semantic paragraph boundaries in full_text.
    # Use those blocks directly instead of the shared size-based chunker,
    # which intentionally combines paragraphs for model processing.
    if paper_data.get("source_type") == "HTML Article":

        narrative_chunks = []

        for block in re.split(r"\n\s*\n", full_text):

            block = block.strip()

            if not block:
                continue

            # _collect_full_text already adds the page marker.
            # Remove it before assigning one marker per block.
            block = re.sub(
                r"^\[PAGE \d+\]\s*",
                "",
                block,
                count=1
            )

            if block:
                narrative_chunks.append(
                    "[PAGE 1]\n" + block
                )

        print(
            "ResearchMind: Using HTML semantic evidence blocks:",
            len(narrative_chunks)
        )

    else:
        # Preserve the existing PDF and other document evidence route.
        narrative_chunks = []

        for chunk in chunks:
            narrative_chunk = re.sub(
                r"(?ms)^RESULT RECORD:\\s*$.*?^END RESULT RECORD\\s*$",
                "",
                str(chunk)
            ).strip()

            if narrative_chunk:
                narrative_chunks.append(narrative_chunk)

    print(
        "ResearchMind: Fast evidence preparation completed. "
        f"Using {len(narrative_chunks)} extracted document chunks "
        "without separate Qwen chunk calls."
    )

    combined_evidence = _fit_evidence_for_qwen(
        narrative_chunks,
        model=model,
        limit_chars=QWEN_FINAL_EVIDENCE_CHARS
    )

    if len(combined_evidence) > QWEN_FINAL_EVIDENCE_CHARS:
        raise OllamaError(
            "Narrative evidence exceeds QWEN_FINAL_EVIDENCE_CHARS."
        )

    if progress_callback:
        progress_callback(0.7)

    print(
        "ResearchMind: Final evidence characters:",
        len(combined_evidence)
    )

    print(
        "ResearchMind: Final deterministic result records:",
        len(deterministic_result_records)
    )

    if is_encyclopedia:
        final_prompt = f"""
You are ResearchMind AI, an expert knowledge analyst.

Analyze the supplied encyclopedia article and create a
comprehensive, technically accurate, evidence-based report.

Write for a beginner while preserving technical depth.
Explain concepts clearly, define important terminology,
and organize related ideas logically.

REPORT STRUCTURE:

1. ARTICLE OVERVIEW
- Article title and subject.
- Main topic and scope.
- Concise explanation of what the article covers.
- Identify the source as an encyclopedia article.

2. CORE CONCEPTS AND DEFINITIONS
- Explain the central concepts.
- Define important technical terminology.
- Explain how the concepts relate to each other.
- Include important distinctions and classifications.

3. HISTORICAL DEVELOPMENT
- Explain important historical milestones.
- Identify dates and developments only when supported.
- Explain how the field evolved over time.

4. TECHNICAL APPROACHES AND METHODS
- Explain the major techniques and approaches discussed.
- Describe how they work at a conceptual level.
- Compare approaches when the supplied evidence supports it.
- Do not present general descriptions as experiments performed
  by the encyclopedia article.

5. IMPORTANT SYSTEMS, MODELS AND TECHNOLOGIES
- Explain important named systems, models and technologies.
- Describe their purpose and relevant characteristics.
- Preserve supported technical details and numerical values.

6. APPLICATIONS AND REAL-WORLD USES
- Explain important application areas.
- Describe practical examples supported by the article.
- Distinguish established applications from emerging possibilities.

7. BENEFITS AND SIGNIFICANCE
- Explain the importance of the subject.
- Describe supported advantages and contributions.
- Distinguish demonstrated capabilities from broader claims.

8. LIMITATIONS, RISKS AND CHALLENGES
- Explain limitations and challenges discussed in the article.
- Cover technical, practical and societal issues when supported.
- Clearly label additional analytical observations.

9. DEBATES AND DIFFERING PERSPECTIVES
- Explain disagreements or competing viewpoints in the article.
- Attribute perspectives only when the evidence supports attribution.
- Do not invent consensus or controversy.

10. OPEN QUESTIONS AND FUTURE DIRECTIONS
- Identify explicitly mentioned unresolved questions.
- Separate article-supported future directions from your own
  clearly labelled analytical suggestions.

11. OVERALL CONCLUSION
- Summarize the most important ideas.
- Explain relationships between the major concepts.
- State what the supplied evidence establishes and what it does not.

12. EVIDENCE QUALITY AND TRACEABILITY
- Distinguish factual statements from interpretation.
- Identify incomplete or unclear extracted evidence.
- Preserve numerical details and available page references.
- Remember that HTML extraction provides one logical page,
  not original printed page numbers.

GLOBAL ACCURACY RULES:

1. Use only the supplied evidence and metadata.
2. Never invent authors, publication dates, citations or sources.
3. Never describe experiments, datasets or results as performed
   by the article unless the evidence explicitly establishes this.
4. Do not mistake examples, historical events or reported studies
   for experiments conducted by the encyclopedia article.
5. Preserve important technical details and numerical values.
6. Distinguish established facts, reported claims and interpretation.
7. Do not invent quotations or attribute statements to authors.
8. Explain technical concepts accurately for beginners.
9. Do not claim that missing extracted information is absent
   from the original encyclopedia article.
10. Clearly identify uncertainty and incomplete extraction.
11. Do not force the article into a research-paper structure.
12. Do not fabricate references or page numbers.

ARTICLE METADATA:
{metadata_context}

EXTRACTED ARTICLE EVIDENCE:
{combined_evidence}

Generate the complete encyclopedia knowledge analysis report
in Markdown.
"""
    else:
        final_prompt = f"""
    You are ResearchMind AI, an expert academic research analyst.

    Create a comprehensive, technically accurate,
    evidence-based research paper analysis report.

    The report must be beginner-friendly while maintaining
    academic depth, technical accuracy and numerical precision.

    Explain:
    - What the researchers investigated.
    - Why they conducted the research.
    - How the proposed method works.
    - What experiments were performed.
    - What the experimental results demonstrate.
    - How results compare with previous approaches.
    - What limitations and research opportunities are supported.

    REPORT STRUCTURE:

    1. PAPER OVERVIEW
    - Paper title.
    - Authors.
    - Publication year.
    - Research domain.
    - Main topic.
    - Concise explanation.

    2. RESEARCH PROBLEM AND MOTIVATION
    - Problem addressed.
    - Why it matters.
    - Shortcomings of previous approaches.
    - Separate author statements from analysis.

    3. RESEARCH OBJECTIVES
    - List objectives supported by evidence.
    - Do not invent objectives.

    4. METHODOLOGY
    - Explain methodology step by step.
    - Describe proposed approach.
    - Explain how it addresses the problem.

    5. MODEL ARCHITECTURE AND TECHNICAL DETAILS
    - Explain architecture and components.
    - Preserve equations, configurations and algorithms.
    - Include training objectives and masking strategies.
    - Preserve token-replacement percentages.
    - Explain terminology for beginners.

    6. DATASETS AND EXPERIMENTAL SETUP
    - Identify each dataset separately.
    - Explain tasks and evaluation setup.
    - Include training and testing splits.
    - Preserve hardware, optimizer, learning rate, batch size,
      epochs, training steps and other configurations.
    - Do not confuse training settings with evaluation results.

    7. EXPERIMENTAL RESULTS AND COMPARISONS

    Present results in a Markdown table:

    | Experiment | Dataset | Task | Model / Configuration | Split | Metric | Exact Result | Baseline / Comparison | Reported Improvement | Page |

    Rules:
    - Give each experiment or result its own row.
    - Never assign a score to the wrong model.
    - Never confuse different metrics.
    - Preserve exact numerical values and units.
    - Keep datasets and experimental conditions separate.
    - Include baseline comparisons only when supported.
    - Do not calculate improvements.
    - Use "Not specified" for missing information.
    - Include page references only when supported.

    After the table, explain the most important findings.

    8. KEY CONTRIBUTIONS AND NOVELTY
    - Identify main contributions.
    - Explain what is new.
    - Distinguish demonstrated contributions from author claims.

    9. LIMITATIONS AND CRITICAL ANALYSIS

    A. Author-stated limitations:
    Only limitations explicitly acknowledged by the authors.

    B. Evidence-based analytical limitations:
    Reasonable observations supported by methodology or results.
    Label these as analytical observations.

    10. FUTURE RESEARCH DIRECTIONS

    A. Author-stated future work:
    Only future work explicitly mentioned by the authors.

    B. Potential future research opportunities:
    Clearly label your own suggestions.

    11. RESEARCH GAP

    A. Explicitly stated research gaps.
    B. Potential research gaps supported by evidence.

    Do not assume missing extracted evidence means
    the original paper does not discuss that topic.

    12. OVERALL CONCLUSION
    - Summarize problem and proposed solution.
    - Explain important experimental findings.
    - Describe contributions.
    - State what evidence does and does not establish.

    13. EVIDENCE QUALITY AND TRACEABILITY
    - Identify claims supported by numerical evidence.
    - Identify claims supported by qualitative evidence.
    - Highlight missing or incomplete evidence.
    - Preserve page references.
    - Distinguish reported facts from interpretation.

    GLOBAL ACCURACY RULES:
    1. Use only supplied evidence and metadata.
    2. Never invent results, authors, datasets or citations.
    3. Preserve important numerical values exactly.
    4. Never combine results from different experiments.
    5. Never assign metrics to the wrong model.
    6. Do not mix training configurations and evaluation results.
    7. Do not fabricate page references.
    8. Distinguish author statements from analysis.
    9. Do not invent author-stated limitations or future work.
    10. Do not guess missing information.
    11. Explain technical terms for beginners.
    12. Use every row in AUTHORITATIVE DETERMINISTIC TABLE RESULTS
        as the source of exact experimental table values.
    13. Never replace, alter, recalculate or omit those exact values.
    14. Do not infer missing dataset, task or baseline information.
    15. Treat the authoritative deterministic results section as a
        separate source from narrative evidence.
    16. Reproduce every supplied deterministic result record in the
        experimental results table. Do not silently omit records.
    17. Keep each model, dataset, split, metric and exact value
        associated with its original record.
    18. When a field is missing, write "Not specified". Never guess.
    19. Do not use narrative summaries to override exact table records.
    20. Do not claim that information is absent from the original paper
        merely because it is missing from the extracted evidence.
    21. If metadata is missing, report "Not available in supplied
        metadata" instead of inventing a title, author or year.
    22. In evidence quality, explicitly identify incomplete extraction
        and distinguish it from information absent in the paper.
    23. Do not claim that all evidence is complete unless the supplied
        evidence actually supports that conclusion.

    PAPER METADATA:
    {metadata_context}

    EXTRACTED PAPER EVIDENCE:
    {combined_evidence}

    Generate the complete research paper report in Markdown.
    """

    if progress_callback:
        progress_callback(0.8)

    final_summary = _ask_qwen(
        final_prompt,
        model=model,
        num_predict=QWEN_FINAL_OUTPUT_TOKENS
    )

    if not final_summary or not final_summary.strip():
        raise OllamaError(
            "Qwen returned an empty final research report."
        )


    # =====================================================
    # DETERMINISTIC DATASET AND RESULTS SECTIONS
    # =====================================================

    if deterministic_result_records and not is_encyclopedia:

        def _report_field(record, field_name):
            value = get_record_field(record, field_name)
            if value is None:
                return "Not specified"

            value = str(value).strip()
            return value if value else "Not specified"

        def _report_cell(value):
            value = str(value).replace("\r", " ").replace("\n", " ")
            value = value.replace("|", r"\|")
            return value.strip()

        # Build dataset coverage directly from extracted records.
        dataset_details = {}

        for record in deterministic_result_records:
            dataset = _report_field(record, "Dataset or benchmark")
            task = _report_field(record, "Task")
            split = _report_field(record, "Evaluation split")

            if dataset == "Not specified":
                continue

            if dataset not in dataset_details:
                dataset_details[dataset] = {
                    "tasks": [],
                    "splits": []
                }

            if task != "Not specified" and task not in dataset_details[dataset]["tasks"]:
                dataset_details[dataset]["tasks"].append(task)

            if split != "Not specified" and split not in dataset_details[dataset]["splits"]:
                dataset_details[dataset]["splits"].append(split)

        dataset_lines = [
            "## 6. Datasets and Experimental Setup",
            "",
            "The following dataset coverage and evaluation splits are taken "
            "directly from the extracted experimental result records.",
            "",
            "| Dataset / Benchmark | Task | Evaluation splits found in extracted results |",
            "|---|---|---|"
        ]

        for dataset, details in dataset_details.items():
            dataset_lines.append(
                "| "
                + _report_cell(dataset)
                + " | "
                + _report_cell(", ".join(details["tasks"]) or "Not specified")
                + " | "
                + _report_cell(", ".join(details["splits"]) or "Not specified")
                + " |"
            )

        dataset_lines.extend([
            "",
            "Note: These are evaluation splits explicitly represented in "
            "the extracted result records. They should not be interpreted "
            "as a complete description of training or validation procedures."
        ])

        # Build every results row directly from the 66 extracted records.
        result_lines = [
            "## 7. Experimental Results and Comparisons",
            "",
            f"The table below contains all {len(deterministic_result_records)} "
            "deterministic experimental result records. Values, model names, "
            "metrics and evaluation splits are reproduced from the extracted records.",
            "",
            "| # | Dataset | Task | Model / Configuration | Split | Metric | Exact Result | Baseline / Comparison | Reported Improvement | Page |",
            "|---:|---|---|---|---|---|---|---|---|---|"
        ]

        for index, record in enumerate(deterministic_result_records, start=1):
            fields = [
                str(index),
                _report_field(record, "Dataset or benchmark"),
                _report_field(record, "Task"),
                _report_field(record, "Model or configuration"),
                _report_field(record, "Evaluation split"),
                _report_field(record, "Metric name"),
                _report_field(record, "Exact reported value"),
                _report_field(record, "Baseline or comparison"),
                _report_field(record, "Reported improvement"),
                _report_field(record, "Page reference")
            ]

            result_lines.append(
                "| " + " | ".join(_report_cell(value) for value in fields) + " |"
            )

        result_lines.extend([
            "",
            "**Interpretation rule:** Baseline comparisons and improvements "
            "are included only when explicitly present in the extracted records. "
            "No missing scores or improvements have been calculated or inferred."
        ])

        # Replace only numbered sections 6 and 7, preserving all other sections.
        report_lines = final_summary.splitlines()

        def _find_numbered_heading(number):
            pattern = re.compile(
                r"^\s{0,3}#{0,6}\s*"
                + str(number)
                + r"\s*[\.\)]\s+",
                re.IGNORECASE
            )

            matches = [
                index
                for index, line in enumerate(report_lines)
                if pattern.match(line)
            ]

            return matches[0] if len(matches) == 1 else None

        heading_6 = _find_numbered_heading(6)
        heading_7 = _find_numbered_heading(7)
        heading_8 = _find_numbered_heading(8)

        if (
            heading_6 is not None
            and heading_7 is not None
            and heading_8 is not None
            and heading_6 < heading_7 < heading_8
        ):
            report_lines = (
                report_lines[:heading_6]
                + dataset_lines
                + [""]
                + result_lines
                + [""]
                + report_lines[heading_8:]
            )

            final_summary = "\n".join(report_lines).strip()

            print(
                "ResearchMind: Replaced sections 6 and 7 with "
                "deterministic extracted data."
            )
            print(
                f"ResearchMind: Dataset coverage: {len(dataset_details)} datasets."
            )
            print(
                f"ResearchMind: Main results table: "
                f"{len(deterministic_result_records)} records."
            )
        else:
            print(
                "ResearchMind WARNING: Could not uniquely identify report "
                "sections 6, 7 and 8. Original Qwen sections were preserved."
            )


    # APPEND ALL AUTHORITATIVE DETERMINISTIC RESULT RECORDS.

    if deterministic_result_records:

        appendix_sections = []

        for index, record in enumerate(
            deterministic_result_records,
            start=1
        ):
            record_body = re.sub(
                r"(?m)^RESULT RECORD:\s*$|^END RESULT RECORD\s*$",
                "",
                str(record)
            ).strip()

            if record_body:
                appendix_sections.append(
                    f"### Extracted Result Record {index}\n\n"
                    f"{record_body}"
                )

        if appendix_sections:
            final_summary = (
                final_summary.rstrip()
                + "\n\n"
                + "## Complete Deterministic Experimental Results\n\n"
                + "These records are preserved from structured PDF "
                  "table extraction, separately from the AI-generated "
                  "research narrative.\n\n"
                + "\n\n".join(appendix_sections)
            )

        print(
            "ResearchMind: Appended "
            f"{len(appendix_sections)} deterministic result records."
        )

    if progress_callback:
        progress_callback(1.0)

    elapsed = time.perf_counter() - start_time

    print(
        f"ResearchMind: Qwen summary completed "
        f"in {elapsed:.2f} seconds."
    )

    return final_summary


# =====================================================
# 13. PROVIDER SELECTION WITH SAFE FALLBACK
# =====================================================


def _normalize_provider(model):

    name = str(model).strip().lower()

    if name in (
        "google gemini",
        "gemini",
        "google"
    ):
        return "gemini"

    if name in (
        "qwen",
        "ollama",
        "local qwen",
        "ollama - qwen 2.5"
    ):
        return "qwen"

    raise ValueError(
        f"Unsupported model selection: {model}"
    )


def _make_result(
    text,
    provider,
    model_name,
    fallback_reason=None,
    fallback_code=None
):

    return {
        "text": text,
        "provider": provider,
        "model": model_name,
        "fallback_used": fallback_reason is not None,
        "fallback_reason": fallback_reason,
        "fallback_code": fallback_code,
    }


def summarize_with_fallback(
    paper_data,
    preferred_provider=PROVIDER_GEMINI,
    progress_callback=None
):

    if not isinstance(paper_data, dict):
        raise TypeError(
            "paper_data must be a dictionary."
        )

    if not paper_data.get("pages"):
        raise ValueError(
            "Paper data does not contain readable pages."
        )

    provider = _normalize_provider(preferred_provider)

    if provider == "qwen":

        text = summarize_with_qwen(
            paper_data,
            progress_callback=progress_callback
        )

        return _make_result(
            text,
            PROVIDER_QWEN,
            QWEN_MODEL
        )

    try:
        print(
            f"ResearchMind: Using Gemini model {GEMINI_MODEL}"
        )

        text = _summarize_with_gemini(
            paper_data,
            model=GEMINI_MODEL,
            progress_callback=progress_callback
        )

        return _make_result(
            text,
            PROVIDER_GEMINI,
            GEMINI_MODEL
        )

    except GeminiUnavailableError as gemini_error:

        print(
            f"ResearchMind: Gemini unavailable "
            f"({gemini_error.reason}): {gemini_error}"
        )

        if is_cloud_deployment():
            raise gemini_error

        print(
            "ResearchMind: Switching to local Qwen fallback."
        )

        try:
            text = summarize_with_qwen(
                paper_data,
                progress_callback=progress_callback
            )

        except OllamaError as qwen_error:
            raise AllProvidersFailedError(
                gemini_error,
                qwen_error
            ) from qwen_error

        return _make_result(
            text,
            PROVIDER_QWEN,
            QWEN_MODEL,
            fallback_reason=str(gemini_error),
            fallback_code=gemini_error.reason
        )


def generate_answer_with_fallback(
    prompt,
    preferred_provider=PROVIDER_GEMINI,
    local_prompt=None,
    max_output_tokens=4096
):

    provider = _normalize_provider(preferred_provider)
    qwen_prompt = local_prompt or prompt

    if provider == "qwen":

        text = _ask_qwen(qwen_prompt)

        return _make_result(
            text,
            PROVIDER_QWEN,
            QWEN_MODEL
        )

    try:
        text = generate_gemini_response(
            prompt,
            model=GEMINI_MODEL,
            max_output_tokens=max_output_tokens
        )

        return _make_result(
            text,
            PROVIDER_GEMINI,
            GEMINI_MODEL
        )

    except GeminiUnavailableError as gemini_error:

        print(
            f"ResearchMind: Gemini unavailable "
            f"({gemini_error.reason})."
        )

        if is_cloud_deployment():
            raise gemini_error

        print("ResearchMind: Using Qwen for chat.")

        try:
            text = _ask_qwen(qwen_prompt)

        except OllamaError as qwen_error:
            raise AllProvidersFailedError(
                gemini_error,
                qwen_error
            ) from qwen_error

        return _make_result(
            text,
            PROVIDER_QWEN,
            QWEN_MODEL,
            fallback_reason=str(gemini_error),
            fallback_code=gemini_error.reason
        )


# =====================================================
# 14. COMPATIBILITY FUNCTIONS
# =====================================================


def summarize_research_paper(
    paper_data,
    model="Google Gemini",
    progress_callback=None
):

    result = summarize_with_fallback(
        paper_data,
        preferred_provider=model,
        progress_callback=progress_callback
    )

    return result["text"]


def summarize_with_gemini(
    paper_data,
    progress_callback=None
):

    return _summarize_with_gemini(
        paper_data,
        model=GEMINI_MODEL,
        progress_callback=progress_callback
    )