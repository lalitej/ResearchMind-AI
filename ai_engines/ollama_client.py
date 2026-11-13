import os
import requests

from dotenv import load_dotenv

load_dotenv()

# =========================================
# OLLAMA CONFIGURATION
# =========================================

OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://localhost:11434"
).rstrip("/")

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "qwen2.5:7b"
)


def _read_int_env(name, default):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# Context window (in tokens) requested from Ollama.
# Ollama's default is small and silently cuts off long prompts.
OLLAMA_NUM_CTX = _read_int_env("OLLAMA_NUM_CTX", 8192)

# Maximum seconds to wait for a local response.
OLLAMA_READ_TIMEOUT = _read_int_env("OLLAMA_READ_TIMEOUT", 600)


# =========================================
# ERROR TYPES
# =========================================

class OllamaError(RuntimeError):
    """Base class for all local Ollama problems."""


class OllamaConnectionError(OllamaError):
    """Ollama is not running or cannot be reached."""


class OllamaModelError(OllamaError):
    """The requested model is not installed in Ollama."""


def _error_detail(response):
    """Extract Ollama's own error message from an HTTP response."""

    try:
        body = response.json()

        if isinstance(body, dict) and body.get("error"):
            return str(body["error"])

    except ValueError:
        pass

    text = (response.text or "").strip()

    return text[:300] if text else "no details provided"


# =========================================
# CHECK OLLAMA CONNECTION
# =========================================

def check_ollama_connection():
    """Check whether the Ollama server is running."""

    try:
        response = requests.get(
            f"{OLLAMA_BASE_URL}/api/tags",
            timeout=10
        )

        response.raise_for_status()
        return True

    except requests.RequestException:
        return False


# =========================================
# GET AVAILABLE MODELS
# =========================================

def get_available_models():
    """Return locally installed Ollama models."""

    try:
        response = requests.get(
            f"{OLLAMA_BASE_URL}/api/tags",
            timeout=10
        )

        response.raise_for_status()

        models = response.json().get("models", [])

        return [
            model["name"]
            for model in models
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
    """Generate a response using a local Ollama model."""

    selected_model = model or OLLAMA_MODEL
    context_size = num_ctx or OLLAMA_NUM_CTX

    if not prompt or not prompt.strip():
        raise ValueError("Prompt cannot be empty.")

    if num_predict is not None and num_predict <= 0:
        raise ValueError(
            "num_predict must be greater than zero."
        )

    # Rough safety check: about 3 characters per token.
    if len(prompt) > context_size * 3:
        print(
            f"Ollama warning: the prompt has {len(prompt):,} "
            f"characters and may exceed the {context_size}-token "
            f"context window, so part of it could be cut off."
        )

    options = {
        "temperature": temperature,
        "num_ctx": context_size
    }

    # Only set an output limit when explicitly requested.
    if num_predict is not None:
        options["num_predict"] = num_predict

    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
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
            timeout=(10, OLLAMA_READ_TIMEOUT)
        )

    except requests.ConnectionError as error:
        raise OllamaConnectionError(
            f"Could not connect to Ollama at {OLLAMA_BASE_URL}. "
            f"Make sure the Ollama application is running."
        ) from error

    except requests.Timeout as error:
        raise OllamaError(
            f"Ollama did not respond within "
            f"{OLLAMA_READ_TIMEOUT} seconds."
        ) from error

    except requests.RequestException as error:
        raise OllamaError(
            f"Ollama request failed: {error}"
        ) from error

    if response.status_code == 404:
        raise OllamaModelError(
            f"Model '{selected_model}' is not installed in Ollama. "
            f"Run: ollama pull {selected_model} "
            f"({_error_detail(response)})"
        )

    if response.status_code != 200:
        raise OllamaError(
            f"Ollama returned HTTP {response.status_code}: "
            f"{_error_detail(response)}"
        )

    try:
        result = response.json()

    except ValueError as error:
        raise OllamaError(
            "Ollama returned an invalid response."
        ) from error

    # Extract generated answer.
    answer = result.get(
        "message", {}
    ).get("content", "")

    if not answer or not answer.strip():
        raise OllamaError(
            "Ollama returned an empty response."
        )

    # Detect responses stopped by the output token limit.
    done_reason = result.get("done_reason")

    if num_predict is not None and done_reason == "length":
        raise OllamaError(
            f"Ollama reached the configured output limit "
            f"of {num_predict} tokens. The response may be incomplete. "
            "Increase num_predict or shorten the prompt."
        )

    # Log Ollama performance statistics without changing generation.
    timing_fields = (
        "prompt_eval_count",
        "prompt_eval_duration",
        "eval_count",
        "eval_duration",
        "total_duration",
        "load_duration",
    )

    print("\n========== OLLAMA GENERATION TIMING ==========")
    for field in timing_fields:
        value = result.get(field)
        if value is not None:
            if field.endswith('_duration'):
                print(f"{field}: {value / 1_000_000_000:.2f} seconds")
            else:
                print(f"{field}: {value}")
    print("==============================================\n")

    return answer.strip()
