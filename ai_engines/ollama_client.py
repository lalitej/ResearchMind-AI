import os
import requests

from dotenv import load_dotenv

load_dotenv()

# =========================================
# OLLAMA CONFIGURATION
# =========================================

def _get_setting(name, default=None):
    value = os.getenv(name)

    if value:
        return value

    try:
        import streamlit as st
        return st.secrets.get(name, default)
    except Exception:
        return default


OLLAMA_API_KEY = _get_setting("OLLAMA_API_KEY", "")

OLLAMA_BASE_URL = _get_setting(
    "OLLAMA_BASE_URL",
    "http://localhost:11434"
).rstrip("/")

OLLAMA_MODEL = _get_setting(
    "OLLAMA_MODEL",
    "qwen2.5:7b"
)

OLLAMA_NUM_CTX = int(
    _get_setting("OLLAMA_NUM_CTX", 8192)
)

OLLAMA_READ_TIMEOUT = int(
    _get_setting("OLLAMA_READ_TIMEOUT", 600)
)

# Support both local and cloud endpoints.
if "ollama.com" in OLLAMA_BASE_URL:
    if not OLLAMA_BASE_URL.endswith("/api"):
        OLLAMA_BASE_URL += "/api"

    if not OLLAMA_API_KEY:
        raise RuntimeError(
            "OLLAMA_API_KEY is missing from deployment secrets."
        )

HEADERS = {
    "Content-Type": "application/json"
}

if OLLAMA_API_KEY:
    HEADERS["Authorization"] = (
        f"Bearer {OLLAMA_API_KEY}"
    )


# =========================================
# ERROR TYPES
# =========================================

class OllamaError(RuntimeError):
    pass


class OllamaConnectionError(OllamaError):
    pass


class OllamaModelError(OllamaError):
    pass


def _error_detail(response):
    try:
        body = response.json()

        if isinstance(body, dict) and body.get("error"):
            return str(body["error"])

    except ValueError:
        pass

    return (response.text or "")[:300]


# =========================================
# CHECK CONNECTION
# =========================================

def check_ollama_connection():

    try:
        response = requests.get(
            f"{OLLAMA_BASE_URL}/tags",
            headers=HEADERS,
            timeout=15
        )

        response.raise_for_status()
        return True

    except requests.RequestException:
        return False


# =========================================
# AVAILABLE CLOUD / LOCAL MODELS
# =========================================

def get_available_models():

    try:
        response = requests.get(
            f"{OLLAMA_BASE_URL}/tags",
            headers=HEADERS,
            timeout=20
        )

        response.raise_for_status()

        models = response.json().get("models", [])

        return [
            model.get("name")
            for model in models
            if model.get("name")
        ]

    except requests.RequestException as error:
        raise OllamaConnectionError(
            f"Could not retrieve Ollama models: {error}"
        ) from error


# =========================================
# CHAT WITH OLLAMA
# =========================================

def chat_with_ollama(
    prompt,
    model=None,
    temperature=0.2,
    num_ctx=None,
    num_predict=None
):

    selected_model = model or OLLAMA_MODEL
    context_size = num_ctx or OLLAMA_NUM_CTX

    if not prompt or not prompt.strip():
        raise ValueError("Prompt cannot be empty.")

    if num_predict is not None and num_predict <= 0:
        raise ValueError(
            "num_predict must be greater than zero."
        )

    # Validate hosted model availability.
    available = get_available_models()

    if selected_model not in available:
        raise OllamaModelError(
            f"Model '{selected_model}' is not available "
            f"through this Ollama endpoint. "
            f"Available models: {', '.join(available[:20])}"
        )

    options = {
        "temperature": temperature,
        "num_ctx": context_size
    }

    if num_predict is not None:
        options["num_predict"] = num_predict

    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/chat",
            headers=HEADERS,
            json={
                "model": selected_model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "stream": False,
                "options": options
            },
            timeout=(15, OLLAMA_READ_TIMEOUT)
        )

        response.raise_for_status()

    except requests.Timeout as error:
        raise OllamaError(
            "Ollama request timed out."
        ) from error

    except requests.RequestException as error:
        detail = (
            _error_detail(error.response)
            if error.response is not None
            else str(error)
        )

        raise OllamaConnectionError(
            f"Ollama request failed: {detail}"
        ) from error

    try:
        result = response.json()

    except ValueError as error:
        raise OllamaError(
            "Ollama returned an invalid response."
        ) from error

    answer = result.get(
        "message", {}
    ).get("content", "")

    if not answer or not answer.strip():
        raise OllamaError(
            "Ollama returned an empty response."
        )

    return answer.strip()
