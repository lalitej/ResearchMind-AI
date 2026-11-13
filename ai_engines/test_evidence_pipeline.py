from unittest.mock import patch
import ai_engines.gemini_client as gemini_module

from ai_engines.gemini_client import (
    _split_evidence_preserving_pages,
    build_document_chunks,
    _fit_evidence_for_qwen,
)

from ai_engines.ollama_client import OllamaError


# =====================================================
# TEST 1: PAGE REFERENCES AND CHUNK SIZE
# =====================================================

def test_page_numbers_and_chunk_size():

    pages = [
        {
            "page_number": 1,
            "text": "Introduction " * 100
        },
        {
            "page_number": 2,
            "text": "Methodology " * 100
        }
    ]

    max_chars = 300

    chunks = build_document_chunks(
        pages,
        max_chunk_chars=max_chars
    )

    print("\n========== TEST 1 ==========")
    print("Generated chunks:", len(chunks))

    for index, chunk in enumerate(chunks, start=1):

        has_marker = "[PAGE " in chunk
        valid_size = len(chunk) <= max_chars

        print(
            f"Chunk {index}: "
            f"Length={len(chunk)}, "
            f"Page marker={has_marker}, "
            f"Within limit={valid_size}"
        )

        assert has_marker, (
            f"Chunk {index} lost its page marker."
        )

        assert valid_size, (
            f"Chunk {index} exceeds {max_chars} characters."
        )

    print("TEST 1 PASSED: Page references and chunk sizes.")


# =====================================================
# TEST 2: OVERSIZED EVIDENCE SAFETY
# =====================================================

def test_oversized_evidence_is_not_truncated():

    evidence = ["A" * 600]

    print("\n========== TEST 2 ==========")

    try:

        _fit_evidence_for_qwen(
            evidence,
            limit_chars=500
        )

    except OllamaError as error:

        print("Error type:", type(error).__name__)
        print("Error message:", error)

        assert "no evidence was truncated" in str(error).lower()
        print(
            "TEST 2 PASSED: Oversized evidence "
            "was safely rejected."
        )

    else:

        raise AssertionError(
            "Oversized evidence was accepted unexpectedly."
        )


# =====================================================
# TEST 3: EVIDENCE SPLITTING
# =====================================================

def test_evidence_splitting():

    page_1 = "Introduction to BERT. " * 40
    page_2 = "Masked language modelling. " * 40
    page_3 = "Experimental results. " * 40

    evidence = (
        "[PAGE 1]\n"
        + page_1
        + "\n[PAGE 2]\n"
        + page_2
        + "\n[PAGE 3]\n"
        + page_3
    )

    expected_pages = {
        "1": page_1 + "\n",
        "2": page_2 + "\n",
        "3": page_3
    }

    max_chars = 200

    pieces = _split_evidence_preserving_pages(
        evidence,
        max_chars=max_chars
    )

    print("\n========== TEST 3 ==========")
    print("Generated pieces:", len(pieces))

    reconstructed_pages = {}
    page_order = []

    for index, piece in enumerate(pieces, start=1):

        has_marker = piece.startswith("[PAGE ")
        valid_size = len(piece) <= max_chars

        print(
            f"Piece {index}: "
            f"Length={len(piece)}, "
            f"Page reference={has_marker}, "
            f"Within limit={valid_size}"
        )

        assert valid_size, (
            f"Piece {index} exceeds the character limit."
        )

        assert has_marker, (
            f"Piece {index} does not start with a page marker."
        )

        header, separator, content = piece.partition("\n")

        assert separator, (
            f"Piece {index} has no content separator."
        )

        assert header.startswith("[PAGE ") and header.endswith("]"), (
            f"Piece {index} has an invalid page marker."
        )

        page_number = header[len("[PAGE "):-1]

        if page_number not in reconstructed_pages:
            reconstructed_pages[page_number] = ""
            page_order.append(page_number)

        reconstructed_pages[page_number] += content

    # Verify that all original page content is preserved
    # without loss, duplication, or reordering.
    assert page_order == ["1", "2", "3"], (
        f"Page order changed: {page_order}"
    )

    assert reconstructed_pages == expected_pages, (
        "Original evidence was lost, duplicated, "
        "or changed during splitting."
    )

    print("Original page content reconstructed successfully.")
    print("Page order preserved.")
    print("No evidence loss or duplication detected.")

    print(
        "TEST 3 PASSED: Size, page markers, "
        "and exact evidence preservation."
    )

# =====================================================
# TEST 4: RESULT RECORD STRUCTURE PRESERVATION
# =====================================================

def test_result_record_structure_preservation():

    record_1 = (
        "RESULT RECORD:\n"
        "- Experiment: BERT base evaluation\n"
        "- Dataset or benchmark: GLUE\n"
        "- Task: MNLI\n"
        "- Model or configuration: BERT Base\n"
        "- Evaluation split: Development\n"
        "- Metric name: Accuracy\n"
        "- Exact reported value: 84.6%\n"
        "- Unit: Percentage\n"
        "- Baseline or comparison: Previous model 82.1%\n"
        "- Reported improvement: 2.5 percentage points\n"
        "- Page reference: 8\n"
        "- Supporting evidence: Reported in the experimental results table."
    )

    record_2 = (
        "RESULT RECORD:\n"
        "- Experiment: BERT large evaluation\n"
        "- Dataset or benchmark: GLUE\n"
        "- Task: MNLI\n"
        "- Model or configuration: BERT Large\n"
        "- Evaluation split: Development\n"
        "- Metric name: Accuracy\n"
        "- Exact reported value: 86.7%\n"
        "- Unit: Percentage\n"
        "- Baseline or comparison: Previous model 84.2%\n"
        "- Reported improvement: 2.5 percentage points\n"
        "- Page reference: 9\n"
        "- Supporting evidence: Reported in a separate results table."
    )

    evidence = (
        "[PAGE 8]\n"
        + record_1
        + "\n[PAGE 9]\n"
        + record_2
    )

    print("\n========== TEST 4 ==========")

    pieces = _split_evidence_preserving_pages(
        evidence,
        max_chars=800
    )

    reconstructed = "\n".join(pieces)

    assert record_1 in reconstructed, (
        "First result record was damaged."
    )

    assert record_2 in reconstructed, (
        "Second result record was damaged."
    )
    assert any(record_1 in piece for piece in pieces), (
    "First RESULT RECORD was split across pieces."
)

    assert any(record_2 in piece for piece in pieces), (
    "Second RESULT RECORD was split across pieces."
)

    assert "84.6%" in reconstructed
    assert "86.7%" in reconstructed

    assert "BERT Base" in reconstructed
    assert "BERT Large" in reconstructed

    assert "[PAGE 8]" in reconstructed
    assert "[PAGE 9]" in reconstructed

    assert all(len(piece) <= 2000 for piece in pieces)

    print("Both result records preserved.")
    print("Model and numerical associations preserved.")
    print("Page references preserved.")
    print("TEST 4 PASSED.")
    # =====================================================
# TEST 5: PROTECTED RESULT RECORDS DURING COMPRESSION
# =====================================================

def test_protected_records_survive_compression():

    record_1 = (
        "RESULT RECORD:\n"
        "- Experiment: BERT base evaluation\n"
        "- Dataset or benchmark: GLUE\n"
        "- Task: MNLI\n"
        "- Model or configuration: BERT Base\n"
        "- Evaluation split: Development\n"
        "- Metric name: Accuracy\n"
        "- Exact reported value: 84.6%\n"
        "- Unit: Percentage\n"
        "- Baseline or comparison: Previous model 82.1%\n"
        "- Reported improvement: 2.5 percentage points\n"
        "- Page reference: 8\n"
        "- Supporting evidence: Experimental results table.\n"
        "END RESULT RECORD"
    )

    record_2 = (
        "RESULT RECORD:\n"
        "- Experiment: BERT large evaluation\n"
        "- Dataset or benchmark: GLUE\n"
        "- Task: MNLI\n"
        "- Model or configuration: BERT Large\n"
        "- Evaluation split: Development\n"
        "- Metric name: Accuracy\n"
        "- Exact reported value: 86.7%\n"
        "- Unit: Percentage\n"
        "- Baseline or comparison: Previous model 84.2%\n"
        "- Reported improvement: 2.5 percentage points\n"
        "- Page reference: 9\n"
        "- Supporting evidence: Separate results table.\n"
        "END RESULT RECORD"
    )

    evidence = (
        "This is a deliberately repetitive explanation. " * 100
        + "\n"
        + record_1
        + "\n"
        + ("Repeated explanatory text. " * 100)
        + "\n"
        + record_2
    )

    def fake_qwen(prompt, model=None, num_predict=None):

        import re

        placeholders = re.findall(
            r"\[\[PROTECTED_RESULT_RECORD_\d{4}\]\]",
            prompt
        )

        # Some batches contain only explanatory evidence.
        # Preserve placeholders whenever they are present.
        return (
            "Compressed research explanation.\n"
            + "\n".join(placeholders)
        )

    print("\n========== TEST 5 ==========")

    with patch.object(
        gemini_module,
        "_ask_qwen",
        side_effect=fake_qwen
    ) as mocked_qwen:

        result = _fit_evidence_for_qwen(
            [evidence],
            limit_chars=2000
        )

    assert record_1 in result, (
        "Original BERT Base result record was not restored."
    )

    assert record_2 in result, (
        "Original BERT Large result record was not restored."
    )

    assert result.index(record_1) < result.index(record_2), (
        "Result record order changed."
    )

    assert "84.6%" in result
    assert "86.7%" in result
    assert "BERT Base" in result
    assert "BERT Large" in result

    assert "[[PROTECTED_RESULT_RECORD_" not in result, (
        "A placeholder was not restored."
    )

    assert not mocked_qwen.called, (
        "Evidence selection unexpectedly called Qwen."
    )

    print("Both original records restored exactly.")
    print("Numerical values and model associations preserved.")
    print("Record order preserved.")
    print("No placeholders leaked into final evidence.")
    print("No unnecessary Qwen API call was made.")
    print("TEST 5 PASSED.")
# =====================================================
# RUN ALL TESTS
# =====================================================

if __name__ == "__main__":

    test_page_numbers_and_chunk_size()

    test_oversized_evidence_is_not_truncated()

    test_evidence_splitting()

    test_result_record_structure_preservation()
    test_protected_records_survive_compression()

    print("\n================================")
    print("ALL EVIDENCE PIPELINE TESTS PASSED")
    print("================================")