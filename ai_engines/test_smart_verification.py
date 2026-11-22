"""Regression tests for targeted Gemini smart verification."""
from unittest.mock import patch

import ai_engines.gemini_client as gemini


SOURCE = (
    "[PAGE 1]\nTitle: A Study of Models\nAuthor: Jane Doe\n"
    "[PAGE 5]\nOn the test set, accuracy was 84.6% compared with 82.1%.\n"
    "The experiment used Dataset X.\n"
    "[PAGE 7]\nThe methodology used randomized sampling and a validation cohort.\n"
    "The limitations include a small sample size."
)


def test_smart_evidence_keeps_opening_and_matching_numeric_context():
    draft = (
        "The test accuracy was 85.6%. The methodology used randomized sampling "
        "and the limitations include a small sample size."
    )
    evidence = gemini._build_smart_verification_evidence(SOURCE, draft)

    assert "[PAGE 1]" in evidence
    assert "Jane Doe" in evidence
    assert "84.6% compared with 82.1%" in evidence
    assert "randomized sampling" in evidence
    assert "small sample size" in evidence
    assert len(evidence) <= gemini.SMART_VERIFY_MAX_EVIDENCE_CHARS


def test_smart_verification_applies_source_supported_exact_correction():
    response = (
        '{"corrections":[{"exact_text":"85.6%",'
        '"replacement_text":"84.6%",'
        '"source_quote":"accuracy was 84.6% compared with 82.1%",'
        '"reason":"The source reports 84.6%."}]}'
    )
    with patch.object(gemini, "generate_gemini_response", return_value=response):
        result = gemini.verify_smart_summary(
            SOURCE, "The test accuracy was 85.6%."
        )

    assert result == "The test accuracy was 84.6%."


def test_smart_verification_rejects_quote_not_present_in_source():
    response = (
        '{"corrections":[{"exact_text":"85.6%",'
        '"replacement_text":"84.6%",'
        '"source_quote":"this quotation is not in the source",'
        '"reason":"unsupported"}]}'
    )
    draft = "The test accuracy was 85.6%."
    with patch.object(gemini, "generate_gemini_response", return_value=response):
        result = gemini.verify_smart_summary(SOURCE, draft)

    assert result == draft


def test_smart_verification_rejects_ambiguous_repeated_target():
    response = (
        '{"corrections":[{"exact_text":"85.6%",'
        '"replacement_text":"84.6%",'
        '"source_quote":"accuracy was 84.6% compared with 82.1%",'
        '"reason":"source-backed"}]}'
    )
    draft = "The test accuracy was 85.6%; the second result was 85.6%."
    with patch.object(gemini, "generate_gemini_response", return_value=response):
        result = gemini.verify_smart_summary(SOURCE, draft)

    assert result == draft


def test_smart_verification_api_failure_preserves_original_draft():
    draft = "Original report with all sections and citations."
    error = gemini.GeminiUnavailableError(
        "server_error", "simulated verification failure"
    )
    with patch.object(gemini, "verify_smart_summary", side_effect=error):
        result = gemini._verify_or_keep_draft(SOURCE, draft, model=None)

    assert result.startswith(draft)
    assert "verification was skipped" in result.lower()
