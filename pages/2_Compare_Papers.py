import hashlib
import streamlit as st
from research_tools.ui import apply_theme, page_header, provider_picker
from research_tools.history_store import init_db, log_event
from research_tools.ai_features import generate_research_output
from document_processing.pdf_reader import extract_pdf

st.set_page_config(page_title="Compare Papers | ResearchMind AI", page_icon="⚖️", layout="wide")
init_db(); apply_theme()
page_header("Cross-paper synthesis", "Compare research papers", "Compare two to five papers across their questions, methods, datasets, findings and limitations.")
provider=provider_picker("compare_provider")
uploads=st.file_uploader("Upload 2–5 research PDFs", type=["pdf"], accept_multiple_files=True, help="Each paper is extracted locally before the comparison prompt is sent to your selected AI provider.")
if uploads:
    if len(uploads)<2 or len(uploads)>5: st.warning("Please select between 2 and 5 PDF papers.")
    else:
        papers=[]
        for file in uploads:
            try:
                data=extract_pdf(file.getvalue())
                if not data.get("success"): st.warning(f"Could not extract readable text from {file.name}."); continue
                data["metadata"]=data.get("metadata") or {}
                if data["metadata"].get("title") in (None,"","Unknown title"):
                    data["metadata"]["title"]=file.name.rsplit(".",1)[0]
                data["source_type"]="Comparison upload"
                papers.append(data)
            except Exception as exc: st.error(f"{file.name}: {exc}")
        if len(papers)>=2:
            st.markdown("### Papers selected")
            for i,p in enumerate(papers,1):
                m=p.get("metadata",{})
                st.write(f"**{i}. {m.get('title','Untitled')}** — {m.get('author','Author not identified')} · {p.get('total_pages',0)} pages")
            focus=st.multiselect("Comparison dimensions",["Research question","Methodology","Datasets and evaluation","Key findings","Contributions","Limitations","Research gaps"],default=["Research question","Methodology","Key findings","Contributions","Limitations"])
            if st.button("Generate paper comparison",type="primary",use_container_width=True):
                task="Compare all supplied papers in a structured table, followed by a synthesis of agreements, disagreements, methodological differences, evidence quality, complementary contributions and open questions. Cover: "+", ".join(focus)+". Cite each claim by paper title and page where available. Do not assume missing information."
                try:
                    with st.spinner("Comparing the selected papers..."):
                        result=generate_research_output(papers,task,provider,max_output_tokens=6000)
                    st.session_state["rm_comparison_result"]=result["text"]
                    log_event("comparison","Multi-paper comparison generated",f"{len(papers)} papers",result["text"])
                except Exception as exc: st.error(f"Comparison failed: {exc}")
if st.session_state.get("rm_comparison_result"):
    st.markdown("---")
    st.markdown(st.session_state["rm_comparison_result"])
    from research_tools.exports import make_docx,make_pdf
    c1,c2=st.columns(2)
    with c1:
        try: st.download_button("Download DOCX",make_docx("Research paper comparison",st.session_state["rm_comparison_result"]),"paper_comparison.docx",mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",use_container_width=True)
        except ImportError: st.caption("Install python-docx for DOCX export.")
    with c2:
        try: st.download_button("Download PDF",make_pdf("Research paper comparison",st.session_state["rm_comparison_result"]),"paper_comparison.pdf",mime="application/pdf",use_container_width=True)
        except ImportError: st.caption("Install reportlab for PDF export.")
