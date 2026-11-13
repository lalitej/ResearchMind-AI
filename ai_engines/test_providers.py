import sys
import traceback

print("=" * 55)
print("       RESEARCHMIND AI 2.0 - PROVIDER TEST")
print("=" * 55)

# --------------------------------------------------
# TEST 1: Import Ollama
# --------------------------------------------------

print("\n[TEST 1] Checking Ollama module...")

try:
    from ai_engines.ollama_client import (
        check_ollama_connection,
        get_available_models,
        chat_with_ollama,
    )

    print("PASS: Ollama module imported successfully.")

except Exception as e:
    print("FAIL: Could not import Ollama module.")
    print(e)
    sys.exit(1)


# --------------------------------------------------
# TEST 2: Import Gemini module
# --------------------------------------------------

print("\n[TEST 2] Checking Gemini module...")

try:
    import ai_engines.gemini_client as gemini

    print("PASS: Gemini module imported successfully.")

except Exception as e:
    print("FAIL: Could not import Gemini module.")
    print(e)
    traceback.print_exc()
    sys.exit(1)


# --------------------------------------------------
# TEST 3: Check Ollama connection
# --------------------------------------------------

print("\n[TEST 3] Checking Ollama connection...")

try:
    connection = check_ollama_connection()
    print("Ollama connection result:", connection)

except Exception as e:
    print("FAIL: Ollama connection check failed.")
    print(e)


# --------------------------------------------------
# TEST 4: Check available Ollama models
# --------------------------------------------------

print("\n[TEST 4] Checking available Ollama models...")

try:
    models = get_available_models()
    print("Available models:", models)

except Exception as e:
    print("FAIL: Could not retrieve Ollama models.")
    print(e)


# --------------------------------------------------
# TEST 5: Test Qwen response
# --------------------------------------------------

print("\n[TEST 5] Testing Qwen response...")

try:
    response = chat_with_ollama(
        "Reply with exactly these words: QWEN TEST SUCCESS"
    )

    print("Qwen response:")
    print(response)

    if response:
        print("PASS: Qwen generated a response.")
    else:
        print("FAIL: Qwen returned an empty response.")

except Exception as e:
    print("FAIL: Qwen response test failed.")
    print(e)


# --------------------------------------------------
# TEST 6: Check fallback functions
# --------------------------------------------------

print("\n[TEST 6] Checking Gemini fallback functions...")

functions_to_check = [
    "summarize_with_fallback",
    "generate_answer_with_fallback",
]

for function_name in functions_to_check:
    if hasattr(gemini, function_name):
        print(f"PASS: {function_name} is available.")
    else:
        print(f"WARNING: {function_name} is missing.")


print("\n" + "=" * 55)
print("              TEST COMPLETED")
print("=" * 55)