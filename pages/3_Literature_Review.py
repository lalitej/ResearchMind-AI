import streamlit as st
from research_tools.ui import apply_theme,page_header,provider_picker
from research_tools.history_store import init_db,get_papers,log_event
from research_tools.ai_features import generate_research_output

st.set_page_config(page_title="Literature Review | ResearchMind AI",page_icon="📚",layout="wide")
init_db(); apply_theme()
page_header("Synthesis workspace","Literature review generator","Build a structured literature review from papers you've imported into your ResearchMind library.")
provider=provider_picker("literature_provider")
papers=get_papers(include_text=True)
if len(papers)<2:
    st.info("Import at least two papers in Research Workspace. Imported papers are automatically added to your local library.")
else:
    options={f"{p['title']} · {p['author'] or 'Author unknown'} · {p['created_at'][:10]}":p for p in papers}
    selected=st.multiselect("Select papers for the review (2–10)",list(options.keys()),max_selections=10)
    topic=st.text_input("Review topic or research question",placeholder="e.g. Transformer architectures for long-document understanding")
    style=st.selectbox("Review structure",["Thematic synthesis","Chronological development","Methodological review","Critical literature review"])
    if st.button("Generate literature review",type="primary",use_container_width=True):
        if len(selected)<2: st.warning("Select at least two papers.")
        elif not topic.strip(): st.warning("Enter a topic or research question.")
        else:
            chosen=[]
            for label in selected:
                p=options[label]
                chosen.append({"title":p["title"],"author":p["author"],"full_text":p.get("full_text","")})
            task=f"Write a rigorous {style.lower()} on: {topic}. Use only the selected source papers. Include an introduction and scope, thematic or chronological synthesis, comparison of methods and findings, areas of consensus and disagreement, limitations of the existing evidence, research gaps, future directions, and a conclusion. Include an evidence matrix with paper title, method, data/sample, key finding and limitation. Cite source titles and page numbers only when available in extracted text; never fabricate bibliographic details."
            try:
                with st.spinner("Synthesizing the selected literature..."):
                    result=generate_research_output(chosen,task,provider,max_output_tokens=7000)
                st.session_state["rm_literature_result"]=result["text"]
                log_event("literature_review","Literature review generated",f"{len(chosen)} papers · {topic}",result["text"])
            except Exception as exc: st.error(f"Literature review failed: {exc}")
if st.session_state.get("rm_literature_result"):
    st.markdown("---")
    st.markdown(st.session_state["rm_literature_result"])
    from research_tools.exports import make_docx,make_pdf
    c1,c2=st.columns(2)
    with c1:
        try: st.download_button("Download DOCX",make_docx("Literature review",st.session_state["rm_literature_result"]),"literature_review.docx",mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",use_container_width=True)
        except ImportError: st.caption("Install python-docx for DOCX export.")
    with c2:
        try: st.download_button("Download PDF",make_pdf("Literature review",st.session_state["rm_literature_result"]),"literature_review.pdf",mime="application/pdf",use_container_width=True)
        except ImportError: st.caption("Install reportlab for PDF export.")
