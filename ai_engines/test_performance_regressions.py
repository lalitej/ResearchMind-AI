"""Offline regression tests for the URL-summarization performance work.

Every Gemini call is mocked; no network access or API key is required.
Run with:  python -m pytest ai_engines/test_performance_regressions.py
"""
import io
import os
import threading
import time
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

import ai_engines.gemini_client as gemini
from document_processing import url_reader


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _article_paper(chars, source_type="HTML Article"):
    """Build paper_data resembling an extracted web article."""
    sentence = "Neural networks reached 95.4% accuracy in 2023 on benchmark data. "
    text = (sentence * (chars // len(sentence) + 1))[:chars]
    return {
        "success": True,
        "source_type": source_type,
        "document_kind": "encyclopedia",
        "metadata": {"title": "Artificial intelligence", "author": "n/a"},
        "pages": [{"page_number": 1, "text": text}],
    }


def _pdf_paper(pages=6, chars_per_page=8000):
    return {
        "success": True,
        "source_type": "PDF",
        "metadata": {"title": "A Study", "author": "Jane Doe"},
        "pages": [
            {
                "page_number": number,
                "text": (f"Page {number} result: accuracy 84.6% on Dataset X. " * 400)[
                    :chars_per_page
                ],
            }
            for number in range(1, pages + 1)
        ],
    }


class FakeGemini:
    """Records generate_gemini_response calls by stage."""

    def __init__(self, verification_json='{"corrections":[]}'):
        self.calls = []
        self.verification_json = verification_json
        self._lock = threading.Lock()

    def __call__(self, prompt, model=None, max_output_tokens=8192,
                 max_attempts=None, stage="request"):
        with self._lock:
            self.calls.append((stage, len(prompt), max_attempts))
        gemini.RUN_STATS.record_request(stage, 0.0)
        if stage == "verification_smart":
            return self.verification_json
        if stage == "chunk":
            return "Evidence: accuracy 84.6% [PAGE 1]"
        return "# 1. Paper Overview\nAccuracy was 95.4% [PAGE 1]."

    def count(self, stage):
        return sum(1 for item in self.calls if item[0] == stage)


def _wiki_html_modern():
    body = "".join(
        f"<p>Section {i} discusses learning systems with 95.4 percent accuracy"
        f'<sup class="reference"><a>[{i}]</a></sup> in 2023. '
        + "Deep learning uses many layers. " * 15
        + "</p>"
        for i in range(30)
    )
    return (
        "<html><head><title>Artificial intelligence - Wikipedia</title></head>"
        '<body><div id="mw-content-text"><div class="mw-parser-output">'
        '<div class="mw-heading mw-heading2"><h2 id="History">History</h2>'
        '<span class="mw-editsection">[edit]</span></div>'
        + body
        + '<div class="mw-heading mw-heading2"><h2 id="References">References</h2></div>'
        '<div class="reflist"><ol class="references"><li>CITATION ENTRY ONE</li></ol></div>'
        '<ul><li>TEXTBOOK BIBLIOGRAPHY ENTRY</li></ul>'
        '<div class="mw-heading mw-heading3"><h3 id="Textbooks">Textbooks</h3></div>'
        '<ul><li>NESTED BIBLIOGRAPHY ENTRY</li></ul>'
        '<div class="mw-heading mw-heading2"><h2 id="Further_reading">Further reading</h2></div>'
        '<ul><li>FURTHER READING ENTRY</li></ul>'
        "</div></div></body></html>"
    )


def _wiki_html_legacy():
    body = "".join(
        f"<p>Legacy paragraph {i} about robotics with value 12.5 units. "
        + "Robots use sensors and actuators. " * 15
        + "</p>"
        for i in range(30)
    )
    return (
        "<html><head><title>Robotics - Wikipedia</title></head><body>"
        '<div id="mw-content-text"><div class="mw-parser-output">'
        '<h2><span class="mw-headline" id="Overview">Overview</span></h2>'
        + body
        + '<h2><span class="mw-headline" id="External_links">External links</span></h2>'
        "<ul><li>EXTERNAL LINK ENTRY</li></ul>"
        "</div></div></body></html>"
    )


# ----------------------------------------------------------------------
# URL extraction
# ----------------------------------------------------------------------

def test_wikipedia_modern_markup_drops_bibliography_keeps_article():
    result = url_reader.extract_html_content(_wiki_html_modern().encode())
    text = result["full_text"]

    assert "Section 0 discusses learning systems" in text
    assert "95.4 percent accuracy" in text
    assert "2023" in text
    for noise in (
        "CITATION ENTRY ONE",
        "TEXTBOOK BIBLIOGRAPHY ENTRY",
        "NESTED BIBLIOGRAPHY ENTRY",
        "FURTHER READING ENTRY",
        "[edit]",
        "[12]",
    ):
        assert noise not in text, noise


def test_wikipedia_legacy_markup_drops_external_links_keeps_article():
    result = url_reader.extract_html_content(_wiki_html_legacy().encode())
    text = result["full_text"]

    assert "Legacy paragraph 0 about robotics with value 12.5 units" in text
    assert "EXTERNAL LINK ENTRY" not in text


def test_non_wikipedia_article_is_not_trimmed():
    html = (
        "<html><head><title>Blog</title></head><body><article>"
        + "<h2>References</h2><p>"
        + "This blog post keeps its references heading and text. " * 30
        + "</p></article></body></html>"
    )
    text = url_reader.extract_html_content(html.encode())["full_text"]
    assert "References" in text
    assert "keeps its references heading" in text


def test_bibliography_trim_failure_never_breaks_extraction():
    with patch.object(
        url_reader,
        "_remove_wikipedia_bibliography_sections",
        side_effect=RuntimeError("boom"),
    ):
        result = url_reader.extract_html_content(_wiki_html_modern().encode())
    assert "Section 0 discusses learning systems" in result["full_text"]


def test_url_is_downloaded_exactly_once():
    downloaded = {
        "content": _wiki_html_modern().encode(),
        "content_type": "text/html; charset=utf-8",
        "final_url": "https://en.wikipedia.org/wiki/Artificial_intelligence",
        "download_time": 0.01,
    }
    with patch.object(url_reader, "download_url", return_value=downloaded) as mocked:
        data = url_reader.extract_research_url(downloaded["final_url"])

    assert mocked.call_count == 1
    assert data["success"] is True
    assert data["source_type"] == "HTML Article"
    assert data["document_kind"] == "encyclopedia"
    assert data["pages"][0]["page_number"] == 1


# ----------------------------------------------------------------------
# Chunking and citations
# ----------------------------------------------------------------------

def test_chunking_respects_limit_has_no_duplicates_and_keeps_page_markers():
    paper = _pdf_paper(pages=10, chars_per_page=9000)
    chunks = gemini.build_document_chunks(paper["pages"], gemini.MAX_CHUNK_CHARS)

    assert chunks
    assert all(len(chunk) <= gemini.MAX_CHUNK_CHARS for chunk in chunks)
    assert len(set(chunks)) == len(chunks)
    joined = "\n".join(chunks)
    for number in range(1, 11):
        assert f"[PAGE {number}]" in joined


# ----------------------------------------------------------------------
# Gemini request counts
# ----------------------------------------------------------------------

def test_long_web_article_uses_one_pass_two_requests():
    fake = FakeGemini()
    paper = _article_paper(150000)  # far above the old 28k direct limit

    with patch.object(gemini, "generate_gemini_response", fake):
        summary = gemini._summarize_with_gemini(paper, model="m")

    assert fake.count("chunk") == 0
    assert fake.count("final_report") == 1
    assert fake.count("verification_smart") == 1
    assert len(fake.calls) == 2
    assert "95.4%" in summary


def test_html_one_pass_can_be_disabled_to_restore_chunking():
    fake = FakeGemini()
    paper = _article_paper(150000)

    with patch.object(gemini, "MAX_DIRECT_HTML_CHARS", 0), patch.object(
        gemini, "generate_gemini_response", fake
    ):
        gemini._summarize_with_gemini(paper, model="m")

    assert fake.count("chunk") >= 2
    assert fake.count("final_report") == 1
    assert fake.count("verification_smart") == 1


def test_pdf_keeps_chunked_pipeline_with_exact_request_counts():
    fake = FakeGemini()
    paper = _pdf_paper(pages=6, chars_per_page=8000)  # ~48k chars > 28k
    expected_chunks = len(
        gemini.build_document_chunks(paper["pages"], gemini.MAX_CHUNK_CHARS)
    )
    assert expected_chunks >= 2

    with patch.object(gemini, "generate_gemini_response", fake):
        gemini._summarize_with_gemini(paper, model="m")

    assert fake.count("chunk") == expected_chunks
    assert fake.count("final_report") == 1
    assert fake.count("verification_smart") == 1
    assert len(fake.calls) == expected_chunks + 2


def test_short_pdf_is_single_pass():
    fake = FakeGemini()
    paper = _pdf_paper(pages=2, chars_per_page=5000)
    with patch.object(gemini, "generate_gemini_response", fake):
        gemini._summarize_with_gemini(paper, model="m")
    assert len(fake.calls) == 2


def test_run_stats_report_stage_requests():
    fake = FakeGemini()
    with patch.object(gemini, "generate_gemini_response", fake):
        gemini._summarize_with_gemini(_article_paper(5000), model="m")
    stats = gemini.get_last_run_stats()
    assert stats["requests"] == 2
    assert stats["requests_by_stage"] == {
        "final_report": 1,
        "verification_smart": 1,
    }
    assert "final_report" in stats["stage_seconds"]


# ----------------------------------------------------------------------
# Smart verification
# ----------------------------------------------------------------------

def test_smart_mode_calls_smart_verifier_not_full_report_verifier():
    paper = _article_paper(3000)
    with patch.object(gemini, "VERIFY_MODE", "smart"), patch.object(
        gemini, "verify_smart_summary", return_value="SMART"
    ) as smart, patch.object(
        gemini, "verify_final_summary", return_value="FULL"
    ) as full:
        result = gemini._verify_or_keep_draft("source text", "draft", "m")

    assert result == "SMART"
    assert smart.call_count == 1
    assert full.call_count == 0


def test_smart_verification_sends_bounded_excerpts_not_whole_source():
    source = "\n".join(
        f"Line {i} reports accuracy {i}.5% on Dataset {i}." for i in range(20000)
    )
    prompts = []

    def capture(prompt, **kwargs):
        prompts.append(prompt)
        return '{"corrections":[]}'

    with patch.object(gemini, "generate_gemini_response", side_effect=capture):
        gemini.verify_smart_summary(source, "Accuracy was 5.5% on Dataset 5.")

    assert len(prompts) == 1
    assert len(prompts[0]) < len(source) / 5
    assert "5.5%" in prompts[0]


def test_smart_verification_uses_limited_attempts():
    with patch.object(
        gemini, "generate_gemini_response", return_value='{"corrections":[]}'
    ) as mocked:
        gemini.verify_smart_summary("Accuracy 84.6% here.", "Accuracy 84.6%.")
    assert mocked.call_args.kwargs["max_attempts"] == gemini.VERIFY_MAX_ATTEMPTS
    assert gemini.VERIFY_MAX_ATTEMPTS <= 2


def test_numeric_evidence_and_citation_markers_survive_verification():
    source = "[PAGE 3]\nThe model scored 84.6% accuracy (n=1,204) on Dataset X."
    draft = "# Results\nThe model scored 85.6% accuracy [PAGE 3]."
    response = (
        '{"corrections":[{"exact_text":"85.6%","replacement_text":"84.6%",'
        '"source_quote":"scored 84.6% accuracy","reason":"source"}]}'
    )
    with patch.object(gemini, "generate_gemini_response", return_value=response):
        result = gemini.verify_smart_summary(source, draft)

    assert "84.6%" in result
    assert "[PAGE 3]" in result
    assert "# Results" in result


def test_failed_verification_keeps_draft_and_does_not_raise():
    with patch.object(gemini, "VERIFY_MODE", "smart"), patch.object(
        gemini,
        "generate_gemini_response",
        side_effect=gemini.GeminiUnavailableError("server_error", "down"),
    ):
        result = gemini._verify_or_keep_draft("Accuracy 1%.", "DRAFT BODY", "m")
    assert result.startswith("DRAFT BODY")


# ----------------------------------------------------------------------
# Retry / timeout behaviour (mocked client; sleeps patched out)
# ----------------------------------------------------------------------

class _Server503(Exception):
    code = 503
    status = "UNAVAILABLE"


def _client_with(side_effects):
    client = MagicMock()
    client.models.generate_content.side_effect = side_effects
    return client


def _ok_response(text="ok"):
    response = MagicMock()
    response.text = text
    return response


def test_retry_recovers_and_records_backoff():
    client = _client_with([_Server503("busy"), _ok_response("done")])
    sleeps = []
    gemini.RUN_STATS.reset()
    gemini.clear_gemini_cooldown()

    with patch.object(gemini, "get_gemini_client", return_value=client), patch.object(
        gemini.time, "sleep", side_effect=sleeps.append
    ):
        text = gemini.generate_gemini_response("prompt", model="m", stage="chunk")

    assert text == "done"
    assert client.models.generate_content.call_count == 2
    assert sleeps == [2]
    stats = gemini.get_last_run_stats()
    assert stats["retries"] == 1
    assert stats["retry_wait_seconds"] == 2.0
    assert stats["failed_requests"] == 1


def test_max_attempts_is_respected_and_bounds_waiting():
    client = _client_with([_Server503("busy")] * 5)
    sleeps = []
    gemini.clear_gemini_cooldown()

    with patch.object(gemini, "get_gemini_client", return_value=client), patch.object(
        gemini.time, "sleep", side_effect=sleeps.append
    ):
        try:
            gemini.generate_gemini_response("p", model="m", max_attempts=2)
            raised = False
        except gemini.GeminiUnavailableError as error:
            raised = error.reason == "server_error"

    assert raised
    assert client.models.generate_content.call_count == 2
    assert sleeps == [2]


def test_daily_quota_error_does_not_retry():
    class Quota(Exception):
        code = 429
        status = "RESOURCE_EXHAUSTED"

    client = _client_with([Quota("quota per day exceeded")] * 3)
    gemini.clear_gemini_cooldown()
    with patch.object(gemini, "get_gemini_client", return_value=client), patch.object(
        gemini.time, "sleep"
    ) as sleeper:
        try:
            gemini.generate_gemini_response("p", model="m")
        except gemini.GeminiUnavailableError as error:
            assert error.reason == "quota_exhausted"
    assert client.models.generate_content.call_count == 1
    assert sleeper.call_count == 0
    gemini.clear_gemini_cooldown()


def test_client_is_created_with_request_timeout_and_key_is_not_logged():
    created = {}

    class FakeClient:
        def __init__(self, **kwargs):
            created.update(kwargs)

    class FakeHttpOptions:
        def __init__(self, timeout=None):
            self.timeout = timeout

    secret = "TEST-SECRET-KEY-123"
    buffer = io.StringIO()
    with patch.dict(os.environ, {"GEMINI_API_KEY": secret}), patch.object(
        gemini.genai, "Client", FakeClient
    ), patch.object(gemini.types, "HttpOptions", FakeHttpOptions, create=True), patch.object(
        gemini, "GEMINI_REQUEST_TIMEOUT_SECONDS", 120
    ), redirect_stdout(buffer):
        gemini.get_gemini_client()

    assert created["http_options"].timeout == 120000
    assert secret not in buffer.getvalue()


def test_client_falls_back_when_sdk_rejects_timeout_option():
    calls = []

    class FakeClient:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    class BadHttpOptions:
        def __init__(self, **kwargs):
            raise TypeError("unsupported")

    with patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), patch.object(
        gemini.genai, "Client", FakeClient
    ), patch.object(gemini.types, "HttpOptions", BadHttpOptions, create=True):
        gemini.get_gemini_client()

    assert calls == [{"api_key": "k"}]


def test_chunk_failure_does_not_wait_for_queued_chunks():
    paper = _pdf_paper(pages=12, chars_per_page=9000)
    started = []

    def failing(prompt, **kwargs):
        started.append(time.perf_counter())
        raise gemini.GeminiUnavailableError("server_error", "down")

    begin = time.perf_counter()
    with patch.object(gemini, "MAX_WORKERS", 2), patch.object(
        gemini, "generate_gemini_response", side_effect=failing
    ):
        try:
            gemini._summarize_with_gemini(paper, model="m")
            raised = False
        except gemini.GeminiUnavailableError:
            raised = True

    assert raised
    assert time.perf_counter() - begin < 5
    total_chunks = len(
        gemini.build_document_chunks(paper["pages"], gemini.MAX_CHUNK_CHARS)
    )
    assert len(started) < total_chunks  # queued chunks were cancelled


# ----------------------------------------------------------------------
# Streamlit-style duplicate execution (single flight)
# ----------------------------------------------------------------------

def _reset_flight_state():
    with gemini._FLIGHT_LOCK:
        gemini._INFLIGHT.clear()
        gemini._RESULT_CACHE.clear()


def test_concurrent_identical_requests_run_pipeline_once():
    _reset_flight_state()
    paper = _article_paper(4000)
    release = threading.Event()
    runs = []

    def slow_pipeline(paper_data, preferred_provider, progress_callback=None):
        runs.append(1)
        if progress_callback:
            progress_callback(0.5)
        release.wait(5)
        return gemini._make_result("SUMMARY", gemini.PROVIDER_GEMINI, "m")

    results = []

    def caller():
        results.append(gemini.summarize_with_fallback(paper, gemini.PROVIDER_GEMINI))

    with patch.object(gemini, "_summarize_with_fallback_uncached", slow_pipeline), patch.object(
        gemini, "_FLIGHT_POLL_SECONDS", 0.01
    ):
        threads = [threading.Thread(target=caller) for _ in range(3)]
        for thread in threads:
            thread.start()
        time.sleep(0.2)
        release.set()
        for thread in threads:
            thread.join(5)

    assert len(runs) == 1
    assert [item["text"] for item in results] == ["SUMMARY"] * 3
    _reset_flight_state()


def test_rerun_after_interrupted_script_reuses_background_result():
    """An interrupted caller must not cancel or duplicate the pipeline."""
    _reset_flight_state()
    paper = _article_paper(4000)
    release = threading.Event()
    runs = []

    def slow_pipeline(paper_data, preferred_provider, progress_callback=None):
        runs.append(1)
        release.wait(5)
        return gemini._make_result("SUMMARY", gemini.PROVIDER_GEMINI, "m")

    class Rerun(BaseException):
        pass

    def interrupting_progress(value):
        raise Rerun()

    with patch.object(gemini, "_summarize_with_fallback_uncached", slow_pipeline), patch.object(
        gemini, "_FLIGHT_POLL_SECONDS", 0.01
    ):
        # First script run: progress callback raises (like Streamlit's rerun).
        def first_run():
            try:
                gemini.summarize_with_fallback(
                    paper, gemini.PROVIDER_GEMINI, progress_callback=interrupting_progress
                )
            except Rerun:
                pass

        # slow_pipeline reports progress via a flag so the poll loop fires.
        original = slow_pipeline

        def reporting(paper_data, preferred_provider, progress_callback=None):
            progress_callback(0.4)
            return original(paper_data, preferred_provider, progress_callback)

        with patch.object(gemini, "_summarize_with_fallback_uncached", reporting):
            first = threading.Thread(target=first_run)
            first.start()
            first.join(3)

            second_result = []
            second = threading.Thread(
                target=lambda: second_result.append(
                    gemini.summarize_with_fallback(paper, gemini.PROVIDER_GEMINI)
                )
            )
            second.start()
            time.sleep(0.2)
            release.set()
            second.join(5)

    assert len(runs) == 1
    assert second_result and second_result[0]["text"] == "SUMMARY"
    _reset_flight_state()


def test_completed_result_is_reused_but_fallback_results_are_not_cached():
    _reset_flight_state()
    paper = _article_paper(4000)
    calls = []

    def good(paper_data, preferred_provider, progress_callback=None):
        calls.append("good")
        return gemini._make_result("GOOD", gemini.PROVIDER_GEMINI, "m")

    with patch.object(gemini, "_summarize_with_fallback_uncached", good):
        first = gemini.summarize_with_fallback(paper, gemini.PROVIDER_GEMINI)
        second = gemini.summarize_with_fallback(paper, gemini.PROVIDER_GEMINI)
    assert first["text"] == second["text"] == "GOOD"
    assert calls == ["good"]

    _reset_flight_state()
    calls.clear()

    def fallback(paper_data, preferred_provider, progress_callback=None):
        calls.append("fallback")
        return gemini._make_result(
            "QWEN", gemini.PROVIDER_QWEN, "q",
            fallback_reason="Gemini down", fallback_code="server_error",
        )

    with patch.object(gemini, "_summarize_with_fallback_uncached", fallback):
        gemini.summarize_with_fallback(paper, gemini.PROVIDER_GEMINI)
        gemini.summarize_with_fallback(paper, gemini.PROVIDER_GEMINI)
    assert calls == ["fallback", "fallback"]
    _reset_flight_state()


def test_different_documents_are_not_conflated():
    _reset_flight_state()
    seen = []

    def echo(paper_data, preferred_provider, progress_callback=None):
        seen.append(paper_data["pages"][0]["text"][:5])
        return gemini._make_result(
            paper_data["pages"][0]["text"][:5], gemini.PROVIDER_GEMINI, "m"
        )

    first = _article_paper(3000)
    second = _article_paper(3000)
    second["pages"][0]["text"] = "ZZZZZ" + second["pages"][0]["text"][5:]

    with patch.object(gemini, "_summarize_with_fallback_uncached", echo):
        a = gemini.summarize_with_fallback(first, gemini.PROVIDER_GEMINI)
        b = gemini.summarize_with_fallback(second, gemini.PROVIDER_GEMINI)
    assert a["text"] != b["text"]
    assert len(seen) == 2
    _reset_flight_state()


def test_pipeline_error_propagates_to_caller_and_is_not_cached():
    _reset_flight_state()
    paper = _article_paper(3000)

    def broken(paper_data, preferred_provider, progress_callback=None):
        raise gemini.GeminiUnavailableError("auth", "bad key")

    with patch.object(gemini, "_summarize_with_fallback_uncached", broken):
        try:
            gemini.summarize_with_fallback(paper, gemini.PROVIDER_GEMINI)
            raised = False
        except gemini.GeminiUnavailableError as error:
            raised = error.reason == "auth"
    assert raised
    assert not gemini._RESULT_CACHE
    _reset_flight_state()


# ----------------------------------------------------------------------
# End-to-end (mocked) URL and PDF summarization keep the result structure
# ----------------------------------------------------------------------

def test_end_to_end_url_summary_keeps_result_structure():
    _reset_flight_state()
    fake = FakeGemini()
    downloaded = {
        "content": _wiki_html_modern().encode(),
        "content_type": "text/html",
        "final_url": "https://en.wikipedia.org/wiki/Artificial_intelligence",
        "download_time": 0.0,
    }
    with patch.object(url_reader, "download_url", return_value=downloaded):
        paper = url_reader.extract_research_url(downloaded["final_url"])

    with patch.object(gemini, "generate_gemini_response", fake), patch.object(
        gemini, "is_cloud_deployment", return_value=True
    ):
        result = gemini.summarize_with_fallback(paper, gemini.PROVIDER_GEMINI)

    assert set(result) == {
        "text", "provider", "model", "fallback_used",
        "fallback_reason", "fallback_code",
    }
    assert result["provider"] == gemini.PROVIDER_GEMINI
    assert result["fallback_used"] is False
    assert len(fake.calls) == 2
    _reset_flight_state()


def test_end_to_end_pdf_summary_keeps_result_structure():
    _reset_flight_state()
    fake = FakeGemini()
    paper = _pdf_paper(pages=6, chars_per_page=8000)
    with patch.object(gemini, "generate_gemini_response", fake):
        result = gemini.summarize_with_fallback(paper, gemini.PROVIDER_GEMINI)
    assert result["text"].startswith("# 1. Paper Overview")
    assert fake.count("chunk") >= 2
    assert fake.count("final_report") == 1
    assert fake.count("verification_smart") == 1
    _reset_flight_state()
