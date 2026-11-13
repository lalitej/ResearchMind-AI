import streamlit as st
from research_tools.ui import apply_theme,page_header,provider_picker
from research_tools.history_store import init_db,save_note,get_notes,save_study_items,get_study_items,record_quiz_attempt,get_quiz_stats,log_event
from research_tools.ai_features import generate_research_output,parse_json_response

st.set_page_config(page_title="Study Tools | ResearchMind AI",page_icon="🧠",layout="wide")
init_db(); apply_theme()
page_header("Active learning","Study tools","Turn a paper into revision material, test your understanding, and keep notes attached to the source.")
paper=st.session_state.get("paper_data")
paper_id=st.session_state.get("paper_record_id")
if not paper or not paper_id:
    st.info("Import a paper in Research Workspace first. Study tools use the active paper and save progress to your local history.")
    st.stop()
provider=provider_picker("study_provider")
flash_key=f"rm_flashcards_{paper_id}"
mcq_key=f"rm_mcqs_{paper_id}"
quiz_key=f"rm_quiz_result_{paper_id}"
slide_key=f"rm_presentation_outline_{paper_id}"
meta=paper.get("metadata") or {}
st.caption(f"Active paper: {meta.get('title','Untitled research paper')}")
tab_flash,tab_quiz,tab_notes,tab_slides=st.tabs(["Flashcards","MCQ practice","Research notes","Presentation outline"])
with tab_flash:
    if st.button("Generate 8 flashcards",type="primary"):
        prompt='Create exactly 8 concise study flashcards from the supplied paper. Return ONLY valid JSON as an array of objects with keys question and answer. Answers must be supported by the paper; include page references in answers when available.'
        try:
            with st.spinner("Creating flashcards..."):
                result=generate_research_output([paper],prompt,provider,instructions="Output strict JSON only.",max_output_tokens=2500)
            cards=parse_json_response(result["text"])
            if not isinstance(cards,list) or not cards: raise ValueError("No flashcards were returned.")
            cards=[c for c in cards if isinstance(c,dict) and c.get("question") and c.get("answer")]
            if not cards: raise ValueError("The flashcard response had no usable question/answer pairs.")
            save_study_items(paper_id,"flashcards",cards)
            st.session_state[flash_key]=cards
        except Exception as exc: st.error(f"Flashcard generation failed: {exc}")
    cards=st.session_state.get(flash_key) or get_study_items(paper_id,"flashcards")
    if cards:
        for i,card in enumerate(cards,1):
            with st.expander(f"Card {i}: {card.get('question','Question')}"):
                st.write(card.get("answer",""))
with tab_quiz:
    if st.button("Generate 5 MCQs",type="primary"):
        prompt='Create exactly 5 multiple-choice questions from this paper. Return ONLY valid JSON array. Each object must have keys question, options (array of exactly 4 strings), answer_index (integer 0-3), and explanation. Avoid ambiguous questions. Use only paper-supported facts.'
        try:
            with st.spinner("Preparing your quiz..."):
                result=generate_research_output([paper],prompt,provider,instructions="Output strict JSON only.",max_output_tokens=3000)
            questions=parse_json_response(result["text"])
            if not isinstance(questions,list) or not questions: raise ValueError("No quiz questions were returned.")
            valid=[]
            for q in questions:
                if isinstance(q,dict) and q.get("question") and isinstance(q.get("options"),list) and len(q["options"])==4 and q.get("answer_index") in [0,1,2,3]: valid.append(q)
            if not valid: raise ValueError("The quiz response did not contain valid four-option questions.")
            save_study_items(paper_id,"mcqs",valid)
            st.session_state[mcq_key]=valid
            st.session_state.pop(quiz_key, None)
        except Exception as exc: st.error(f"Quiz generation failed: {exc}")
    questions=st.session_state.get(mcq_key) or get_study_items(paper_id,"mcqs")
    if questions:
        with st.form("rm_quiz_form"):
            answers=[]
            for i,q in enumerate(questions):
                st.markdown(f"**{i+1}. {q['question']}**")
                choice=st.radio("Choose one answer",q["options"],key=f"rm_quiz_{paper_id}_{i}",index=None,label_visibility="collapsed")
                answers.append(q["options"].index(choice) if choice in q["options"] else None)
            submitted=st.form_submit_button("Submit answers",type="primary",use_container_width=True)
        if submitted:
            score=sum(1 for a,q in zip(answers,questions) if a==q["answer_index"])
            record_quiz_attempt(paper_id,score,len(questions),answers)
            st.session_state[quiz_key]={"score":score,"total":len(questions),"answers":answers}
        result=st.session_state.get(quiz_key)
        if result:
            st.metric("Latest score",f"{result['score']} / {result['total']}")
            for i,q in enumerate(questions):
                correct=result["answers"][i]==q["answer_index"]
                st.write(("✅" if correct else "❌")+f" {i+1}. {q['explanation']}")
        stats=get_quiz_stats(paper_id)
        st.caption(f"Saved attempts: {stats['attempts']} · Best score: {stats['best_score']}/{stats['total']}")
with tab_notes:
    note=st.text_area("Add a note about this paper",height=150,placeholder="Record an insight, question, key concept, or idea to revisit...")
    if st.button("Save note",type="primary",disabled=not note.strip()):
        save_note(paper_id,note.strip()); st.success("Note saved to your learning history.")
    notes=get_notes(paper_id)
    if notes:
        st.markdown("### Previous notes")
        for item in notes:
            with st.expander(item["created_at"]): st.write(item["content"])

with tab_slides:
    st.markdown("Create a presentation structure grounded in the active paper.")
    audience=st.selectbox("Presentation audience",["Undergraduate students","Research peers","Academic conference","General audience"])
    slide_count=st.slider("Number of slides",5,15,10)
    if st.button("Generate presentation outline",type="primary"):
        prompt=f"Create a {slide_count}-slide presentation outline for {audience}. For every slide provide a concise title, 3–5 key bullet points, suggested visual (if appropriate), and speaker notes. Cover the research problem, background, methods, results, interpretation, limitations and conclusion as relevant. Do not invent findings."
        try:
            with st.spinner("Building your presentation outline..."):
                result=generate_research_output([paper],prompt,provider,max_output_tokens=3500)
            st.session_state[slide_key]=result["text"]
            log_event("presentation","Presentation outline generated",f"{slide_count} slides · {audience}",result["text"],paper_id)
        except Exception as exc: st.error(f"Presentation outline failed: {exc}")
    if st.session_state.get(slide_key):
        st.markdown(st.session_state[slide_key])
        from research_tools.exports import make_docx,make_pdf
        c1,c2=st.columns(2)
        with c1:
            try: st.download_button("Download outline DOCX",make_docx("Research presentation outline",st.session_state[slide_key]),"presentation_outline.docx",mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",use_container_width=True)
            except ImportError: st.caption("Install python-docx for DOCX export.")
        with c2:
            try: st.download_button("Download outline PDF",make_pdf("Research presentation outline",st.session_state[slide_key]),"presentation_outline.pdf",mime="application/pdf",use_container_width=True)
            except ImportError: st.caption("Install reportlab for PDF export.")
