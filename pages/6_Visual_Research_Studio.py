import json
import re

import streamlit as st

from research_tools.ai_features import generate_research_output, parse_json_response
from research_tools.history_store import init_db, log_event
from research_tools.ui import apply_theme, page_header, provider_picker

st.set_page_config(
    page_title="Visual Research Studio | ResearchMind AI",
    page_icon="🧩",
    layout="wide",
)
init_db()
apply_theme()
page_header(
    "Understand complex ideas",
    "Visual Research Studio",
    "Turn the active research paper into a structured concept map, methodology flow, process diagram or model architecture.",
)

paper = st.session_state.get("paper_data")
paper_id = st.session_state.get("paper_record_id")
if not paper or not paper_id:
    st.info("Import a research paper in Research Workspace first. Visual diagrams are generated from the active paper.")
    st.stop()

metadata = paper.get("metadata") or {}
paper_title = metadata.get("title") or "Untitled research paper"
st.markdown(f"**Active source:** {paper_title}")
st.caption("Diagrams are AI-generated interpretations of extracted paper text. Check each connection against the cited pages before using it academically.")

provider = provider_picker("visual_studio_provider")
visual_type = st.selectbox(
    "Choose a visual format",
    [
        "Concept map",
        "Methodology flowchart",
        "Research process diagram",
        "Model / system architecture",
    ],
)
concept = st.text_input(
    "Focus concept (optional)",
    placeholder="e.g. attention mechanism, experimental pipeline, proposed model...",
    help="Leave blank to let the AI identify the most important structure in the paper.",
)
complexity = st.select_slider("Diagram detail", options=["Simple", "Balanced", "Detailed"], value="Balanced")

# Keep the model's evidence context bounded and explicitly page-labelled.
def build_source_context(data, limit=18000):
    pages = data.get("pages") or []
    chunks = []
    if pages:
        for page in pages:
            if not isinstance(page, dict):
                continue
            text = str(page.get("text") or "").strip()
            if not text:
                continue
            number = page.get("page_number", 1)
            chunks.append(f"[PAGE {number}]\n{text}")
    else:
        full_text = str(data.get("full_text") or "")
        chunks = [full_text]
    result = "\n\n".join(chunks)
    if len(result) > limit:
        result = result[:limit] + "\n\n[EXTRACTED SOURCE CONTEXT TRUNCATED]"
    return result


def valid_page_numbers(data):
    pages = data.get("pages") or []
    found = set()
    for page in pages:
        if isinstance(page, dict):
            try:
                found.add(int(page.get("page_number", 1)))
            except (TypeError, ValueError):
                pass
    return found


def dot_escape(value):
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def build_dot(diagram):
    lines = [
        "digraph ResearchDiagram {",
        'graph [rankdir=TB, bgcolor="transparent", pad="0.25", nodesep="0.38", ranksep="0.58", splines=ortho];',
        'node [shape=box, style="rounded,filled", fillcolor="#EAF4EF", color="#28765B", fontname="Arial", fontsize=10, margin="0.16,0.10"];',
        'edge [color="#718078", fontname="Arial", fontsize=9, arrowsize=0.7];',
    ]
    nodes = diagram.get("nodes", [])
    for node in nodes:
        node_id = str(node["id"])
        label = str(node.get("label", "Concept"))
        refs = node.get("page_refs") or []
        suffix = f"\n[Pages {', '.join(map(str, refs))}]" if refs else "\n[Page reference unavailable]"
        lines.append(f'"{dot_escape(node_id)}" [label="{dot_escape(label)}{suffix}"];')
    for edge in diagram.get("edges", []):
        source, target = str(edge["source"]), str(edge["target"])
        label = dot_escape(edge.get("label", ""))
        lines.append(f'"{dot_escape(source)}" -> "{dot_escape(target)}" [label="{label}"];')
    lines.append("}")
    return "\n".join(lines)


def validate_diagram(payload, available_pages):
    if not isinstance(payload, dict):
        raise ValueError("The AI response did not contain a diagram object.")
    nodes = payload.get("nodes")
    edges = payload.get("edges")
    if not isinstance(nodes, list) or not 2 <= len(nodes) <= 14:
        raise ValueError("The diagram must contain between 2 and 14 nodes. Please regenerate it.")
    if not isinstance(edges, list) or len(edges) > 24:
        raise ValueError("The diagram connections were not in the expected format. Please regenerate it.")
    ids = set()
    cleaned_nodes = []
    for index, node in enumerate(nodes, 1):
        if not isinstance(node, dict):
            continue
        node_id = re.sub(r"[^A-Za-z0-9_]", "", str(node.get("id") or f"node_{index}"))[:30]
        if not node_id or node_id in ids:
            node_id = f"node_{index}"
        ids.add(node_id)
        label = str(node.get("label") or "").strip()[:100]
        if not label:
            continue
        refs = []
        for ref in node.get("page_refs", []):
            try:
                page_num = int(ref)
            except (TypeError, ValueError):
                continue
            if page_num in available_pages and page_num not in refs:
                refs.append(page_num)
        cleaned_nodes.append({
            "id": node_id,
            "label": label,
            "detail": str(node.get("detail") or "").strip()[:500],
            "page_refs": refs,
        })
    valid_ids = {node["id"] for node in cleaned_nodes}
    cleaned_edges = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        source, target = str(edge.get("source", "")), str(edge.get("target", ""))
        if source in valid_ids and target in valid_ids and source != target:
            cleaned_edges.append({"source": source, "target": target, "label": str(edge.get("label") or "")[:80]})
    if len(cleaned_nodes) < 2 or not cleaned_edges:
        raise ValueError("The diagram did not contain enough valid nodes and connections. Try a different focus concept.")
    return {
        "title": str(payload.get("title") or visual_type)[:120],
        "description": str(payload.get("description") or "")[:800],
        "nodes": cleaned_nodes,
        "edges": cleaned_edges,
    }


source_context = build_source_context(paper)
if not source_context.strip():
    st.error("No readable extracted text is available for this paper. Re-import the PDF or URL and try again.")
    st.stop()

if st.button("Generate research diagram", type="primary", use_container_width=True):
    task = f"Create a {visual_type.lower()} from this research paper. Focus: {concept.strip() if concept.strip() else 'identify the most important structure in the paper'}. Detail level: {complexity}."
    prompt = f"""You are creating a source-grounded academic diagram.
Return ONLY valid JSON (no Markdown fences) with this exact schema:
{{
  "title": "short diagram title",
  "description": "one or two sentences explaining the diagram",
  "nodes": [{{"id":"n1","label":"short visible label","detail":"brief explanation","page_refs":[1]}}],
  "edges": [{{"source":"n1","target":"n2","label":"short relationship"}}]
}}
Requirements:
- Create 2 to 14 nodes and meaningful directed connections.
- Use only concepts and relationships supported by the supplied extracted text.
- Each node's page_refs must contain only page numbers explicitly shown in [PAGE N] markers.
- Do not invent page numbers, results, steps, components or causal relationships.
- Keep labels concise; put explanations in detail.
- If the requested diagram type is not fully described in the paper, diagram only what is stated and mention the limitation in description.
- Avoid adding generic background knowledge as if it came from the paper.

TASK: {task}

PAPER TITLE: {paper_title}
"""
    try:
        with st.spinner("Reading the paper evidence and constructing your diagram..."):
            result = generate_research_output(
                [
                    {
                        "metadata": {"title": paper_title},
                        "full_text": source_context,
                    }
                ],
                prompt,
                provider,
                instructions="Return strict JSON only. Never create unsupported relationships or page references.",
                max_output_tokens=2600,
            )
        parsed = parse_json_response(result["text"])
        diagram = validate_diagram(parsed, valid_page_numbers(paper))
        dot = build_dot(diagram)
        st.session_state[f"rm_visual_diagram_{paper_id}"] = diagram
        st.session_state[f"rm_visual_dot_{paper_id}"] = dot
        st.session_state[f"rm_visual_provider_{paper_id}"] = result.get("provider", provider)
        history_content = (
            f"**{diagram['title']}**\n\n{diagram['description']}\n\n"
            + "\n".join(
                f"- **{node['label']}** — {node['detail']} (Pages: {', '.join(map(str, node['page_refs'])) if node['page_refs'] else 'not verified'})"
                for node in diagram["nodes"]
            )
        )
        log_event("visual_diagram", "Research diagram generated", f"{visual_type} · {result.get('provider', provider)}", history_content, paper_id)
        st.success("Diagram generated and added to your research history.")
    except Exception as exc:
        st.error(f"Diagram generation failed: {exc}")

diagram = st.session_state.get(f"rm_visual_diagram_{paper_id}")
dot = st.session_state.get(f"rm_visual_dot_{paper_id}")
if diagram and dot:
    st.divider()
    st.subheader(diagram.get("title", "Research diagram"))
    st.write(diagram.get("description", ""))
    st.caption(f"Generated by {st.session_state.get(f'rm_visual_provider_{paper_id}', provider)} · Source: {paper_title}")
    st.graphviz_chart(dot, use_container_width=True)
    st.markdown("### Diagram components and evidence")
    for node in diagram["nodes"]:
        with st.expander(f"{node['label']} · Pages {', '.join(map(str, node['page_refs'])) if node['page_refs'] else 'not verified'}"):
            st.write(node.get("detail") or "No additional explanation supplied.")
            if not node["page_refs"]:
                st.warning("No valid page reference was returned for this component. Verify it manually in the source paper.")
    st.download_button(
        "Download editable Graphviz diagram (.dot)",
        data=dot,
        file_name="researchmind_diagram.dot",
        mime="text/vnd.graphviz",
        use_container_width=True,
    )
    with st.expander("View diagram source (DOT)"):
        st.code(dot, language="dot")
