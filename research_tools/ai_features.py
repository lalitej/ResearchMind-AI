import json
import re

from ai_engines.gemini_client import generate_answer_with_fallback


def generate_research_output(papers, task: str, provider: str, instructions: str = "", max_output_tokens: int = 4096):
    """Run an explicitly scoped task against one or more extracted papers."""
    if not papers:
        raise ValueError("At least one research paper is required.")
    sections = []
    per_paper_limit = max(2500, 18000 // max(len(papers), 1))
    for index, paper in enumerate(papers, 1):
        metadata = paper.get("metadata") or {}
        title = metadata.get("title") or paper.get("title") or f"Paper {index}"
        author = metadata.get("author") or paper.get("author") or "Not specified"
        text = paper.get("full_text") or ""
        if not text and paper.get("pages"):
            text = "\n\n".join(
                f"[PAGE {p.get('page_number', 1)}]\n{p.get('text', '')}"
                for p in paper["pages"] if isinstance(p, dict)
            )
        clipped = text[:per_paper_limit]
        if len(text) > per_paper_limit:
            clipped += "\n[Source text shortened to fit the analysis context. Use only the visible evidence.]"
        sections.append(f"PAPER {index}: {title}\nAUTHOR: {author}\nSOURCE TEXT:\n{clipped}")
    prompt = f"""You are ResearchMind AI, an academic research assistant.
TASK:
{task}

RESEARCH MATERIAL (use only these supplied sources for paper-specific claims):
{chr(10).join(sections)}

ADDITIONAL INSTRUCTIONS:
{instructions or 'Use clear academic language, distinguish evidence from interpretation, and cite paper/page references where the source text provides them.'}

Rules:
- Do not invent authors, findings, numerical results, citations, or page numbers.
- If the supplied text does not support a claim, label it as not stated or not verifiable from the provided text.
- For multiple papers, identify which paper supports each comparison or synthesis.
- Return a useful, well-structured answer in Markdown unless valid JSON is explicitly requested.
"""
    result = generate_answer_with_fallback(
        prompt=prompt,
        preferred_provider=provider,
        max_output_tokens=max_output_tokens,
    )
    if not isinstance(result, dict) or not str(result.get("text", "")).strip():
        raise ValueError("The selected AI provider returned an empty or invalid response.")
    return result


def parse_json_response(text: str):
    cleaned = re.sub(r"^\s*```(?:json)?\s*", "", str(text), flags=re.I)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start_obj, end_obj = cleaned.find("{"), cleaned.rfind("}")
        start_arr, end_arr = cleaned.find("["), cleaned.rfind("]")
        candidates = []
        if start_obj >= 0 and end_obj > start_obj:
            candidates.append(cleaned[start_obj:end_obj + 1])
        if start_arr >= 0 and end_arr > start_arr:
            candidates.append(cleaned[start_arr:end_arr + 1])
        for candidate in candidates:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
    raise ValueError("The AI response was not valid JSON. Try generating the study set again.")
