import streamlit as st
from research_tools.ui import apply_theme,page_header
from research_tools.history_store import init_db,get_papers,get_events

st.set_page_config(page_title="History | ResearchMind AI",page_icon="🕘",layout="wide")
init_db(); apply_theme()
page_header("Your research journey","Learning history","A persistent record of papers explored, summaries generated, questions asked, notes saved and study sessions completed.")
papers=get_papers()
events=get_events(limit=500)
c1,c2,c3=st.columns(3)
c1.metric("Papers in library",len(papers))
c2.metric("Activities recorded",len(events))
c3.metric("Study activities",sum(1 for e in events if e["event_type"] in ("flashcards","mcqs","quiz","note","presentation")))
if papers:
    labels={"All papers":None}
    labels.update({p["title"]:p["id"] for p in papers})
    selected=st.selectbox("Filter history by paper",list(labels.keys()))
    chosen_id=labels[selected]
    visible=get_events(chosen_id,limit=500)
    st.markdown("### Research library")
    for p in papers:
        with st.expander(f"{p['title']} · {p['created_at'][:10]}"):
            st.write(f"Author: {p['author'] or 'Not identified'}")
            st.caption(f"{p['source_type']} · {p['total_pages']} pages · {p['total_words']:,} words")
            if p.get("source_url"): st.markdown(f"[Open source paper]({p['source_url']})")
            if p.get("summary"): st.markdown(p["summary"][:1800]+("…" if len(p["summary"])>1800 else ""))
else:
    visible=events
    st.info("Your history will appear here automatically after you import and explore research papers.")
st.markdown("### Activity timeline")
if not visible:
    st.caption("No activities recorded for this filter yet.")
else:
    icons={"paper_import":"📄","summary":"✨","question":"❓","answer":"🤖","analysis":"🔬","comparison":"⚖️","literature_review":"📚","note":"📝","flashcards":"🗂️","mcqs":"🧩","quiz":"🎯"}
    for event in visible:
        label=event.get("paper_title") or event.get("title") or "Research activity"
        with st.container(border=True):
            st.markdown(f"**{icons.get(event['event_type'],'•')} {event['title']}** · {label}")
            st.caption(f"{event['created_at']} · {event['detail']}")
            if event.get("content") and event["event_type"] in ("question","answer","summary","note","analysis","comparison","literature_review","flashcards","mcqs","quiz","presentation"):
                with st.expander("View saved content"):
                    st.markdown(event["content"][:6000])
