import ai_engines.gemini_client as gemini


# --------------------------------------------------
# SIMULATE A GEMINI QUOTA ERROR
# --------------------------------------------------

def simulate_gemini_failure(*args, **kwargs):
    raise gemini.GeminiUnavailableError(
        reason="quota_exhausted",
        message="SIMULATED: Gemini daily quota exhausted."
    )


# Replace Gemini API call with our simulated failure.
gemini.generate_gemini_response = simulate_gemini_failure


# --------------------------------------------------
# TEST GEMINI -> QWEN CHAT FALLBACK
# --------------------------------------------------

print("=" * 55)
print("       GEMINI TO QWEN FALLBACK TEST")
print("=" * 55)

try:
    result = gemini.generate_answer_with_fallback(
        prompt="Explain artificial intelligence in two sentences.",
        preferred_provider=gemini.PROVIDER_GEMINI
    )

    print("\nProvider:", result["provider"])
    print("Model:", result["model"])
    print("Fallback used:", result["fallback_used"])
    print("Fallback reason:", result["fallback_code"])

    print("\nQwen response:")
    print(result["text"])

    assert result["fallback_used"] is True
    assert result["fallback_code"] == "quota_exhausted"
    assert result["provider"] == gemini.PROVIDER_QWEN
    assert result["text"].strip()

    print("\nPASS: Gemini failure successfully triggered Qwen.")

except Exception as error:
    print("\nFAIL: Fallback test failed.")
    print(type(error).__name__, error)

    raise

print("\n" + "=" * 55)
print("             TEST COMPLETED")
print("=" * 55)