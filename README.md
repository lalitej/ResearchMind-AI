# ResearchMind AI — upgraded workspace

This version keeps the existing PDF/URL import, paper summary, paper-grounded chat, and Gemini → Ollama/Qwen fallback, while adding a redesigned workspace and research/study pages.

## Included sections

- **Research Workspace** — import PDFs or research URLs, view extracted paper details and summaries, and chat with page-grounded context.
- **Advanced Analysis** — methodology, contributions, results, strengths, limitations, research gaps and future directions.
- **Compare Papers** — compare 2–5 uploaded PDFs.
- **Literature Review** — synthesize papers already imported into the local library.
- **Study Tools** — flashcards, MCQ practice, notes and presentation outlines.
- **History** — SQLite-backed paper library and activity timeline for imports, summaries, questions, answers, analyses and study activities.

The interface includes a refreshed academic visual style and a light/dark appearance toggle in the sidebar.

## Setup (Windows PowerShell)

Activate your existing virtual environment, then install the updated dependencies:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Keep your existing `.env` / Streamlit secrets outside the ZIP. The app continues to use your configured Gemini and Ollama settings. For local Qwen, make sure Ollama is running and the configured model is installed.

Run the application:

```powershell
python -m streamlit run app.py
```

Streamlit automatically discovers the feature pages in `pages/`. Imported papers, summaries, notes, study items and activity history are stored locally in `data/researchmind_history.db`; this database is created automatically and is not included in the source ZIP.

## Important notes

- Install the new `beautifulsoup4`, `python-docx` and `reportlab` dependencies via `requirements.txt`.
- AI-generated analysis, comparison and study material should be checked against the original paper before academic submission.
- The literature-review and comparison tools use extracted text supplied to the model. They do not fabricate missing source details intentionally; verify every citation and claim.
- The uploaded original ZIP was left untouched. This upgraded ZIP omits redundant backup copies from the runtime package; the original uploaded archive remains the recovery copy.
## Deploy on Streamlit Community Cloud

1. Push this project to GitHub without .env, databases, virtual environments, or backup files.
2. Create a Streamlit Community Cloud app using your GitHub repository and pp.py.
3. Open App Settings > Secrets and add:

GEMINI_API_KEY = "your-gemini-api-key"
RESEARCHMIND_CLOUD = "true"

Replace the placeholder with your actual key inside Streamlit Cloud Secrets only. Never commit your real key to GitHub.

4. Save the Secrets and deploy or reboot the app.

Cloud mode uses Gemini and disables local Ollama/Qwen because your personal computer's Ollama service is not automatically accessible from Streamlit Cloud.

Note: SQLite history on Streamlit Cloud may be lost after restarts or redeployments.

## Gemini performance and verification settings

Gemini now uses **targeted smart verification** by default. It checks high-risk claims against selected source excerpts and applies only minimal, exact corrections supported by a verbatim source quote. It does not regenerate the complete report during verification, and it preserves report headings, citation markers and page references unless a supported factual correction is required.

Optional environment settings (also usable in Streamlit Secrets):

- `GEMINI_VERIFICATION_MODE=smart` (default): targeted evidence audit.
- `GEMINI_VERIFICATION_MODE=full`: use the previous full-report verification pass.
- `GEMINI_VERIFICATION_MODE=off`: disable the additional verification request.
- `GEMINI_VERIFY_SUMMARY=false`: backward-compatible override that disables verification.
- `GEMINI_SMART_VERIFY_MAX_EVIDENCE_CHARS=24000`: maximum source-excerpt characters supplied to smart verification.

Gemini request timing is logged with model name, prompt size, response size and elapsed seconds. These measurements help distinguish model latency from local document-processing time without logging API keys or prompt contents.

### Performance and run-time settings (added)

- `GEMINI_DIRECT_HTML_CHARS=400000` (default): web articles up to this size are summarized in one Gemini pass (report + smart verification = 2 requests) instead of chunk extraction + report + verification. PDFs keep the original 28,000-character one-pass threshold. Set to `0` to restore chunked processing for web articles.
- `GEMINI_REQUEST_TIMEOUT_SECONDS=180`: per-request timeout so a stalled call cannot block a run indefinitely (retried by the existing retry logic).
- `GEMINI_MAX_WORKERS=3`: parallel chunk requests (PDF/very long documents).
- `GEMINI_VERIFY_MAX_ATTEMPTS=2`: attempts for the optional smart-verification request; on failure the draft report is kept.
- Identical summarization requests (for example a Streamlit rerun while a summary is running) join the in-flight run or reuse its finished result instead of starting a second pipeline. Results produced through the Qwen fallback are never reused.
- Every run logs a `ResearchMind: Run summary | ...` line with Gemini request count, per-stage counts and seconds, retries and retry wait time. No prompts or keys are logged.
- Wikipedia extraction now drops inline citation markers, edit links and bibliography sections (References, Further reading, External links, etc.).
- Keep `RESEARCHMIND_CLOUD=true` on Streamlit Cloud so a Gemini failure surfaces immediately instead of attempting the local Qwen fallback.
