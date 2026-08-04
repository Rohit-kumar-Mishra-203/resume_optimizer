import streamlit as st
import requests

API_BASE = "http://127.0.0.1:8000"

st.set_page_config(page_title="Resume Optimizer", page_icon="🎯", layout="centered")

st.title("Resume Optimizer")
st.caption("Upload your resume once. Paste a job description. Watch it get tailored.")

# ---------- Step 1: Upload resume ----------
st.subheader("Step 1 — Your resume")
resume_file = st.file_uploader("Upload your resume (.tex)", type=["tex"])

if resume_file is not None:
    if st.session_state.get("last_uploaded") != resume_file.name:
        with st.spinner("Parsing resume..."):
            try:
                files = {"file": (resume_file.name, resume_file.getvalue())}
                res = requests.post(f"{API_BASE}/upload-resume", files=files)
                res.raise_for_status()
                data = res.json()
                st.session_state["last_uploaded"] = resume_file.name
                st.success(
                    f"Parsed: {data['experience_count']} jobs, "
                    f"{data['project_count']} projects, "
                    f"{data['skill_count']} skills."
                )
            except Exception as e:
                st.error(f"Upload failed - is the backend running? ({e})")

# ---------- Step 2: Job description ----------
st.subheader("Step 2 — Job description")
jd_text = st.text_area("Paste the full job description here", height=220)

col1, col2 = st.columns(2)
with col1:
    target_score = st.number_input("Target score", min_value=1, max_value=100, value=93)
with col2:
    max_iterations = st.number_input("Max iterations", min_value=1, max_value=15, value=6)

run_clicked = st.button("Run optimization", type="primary", use_container_width=True)

# ---------- Run + Results ----------
if run_clicked:
    if not jd_text.strip():
        st.warning("Paste a job description first.")
    else:
        with st.spinner("Running the optimization loop - this can take a minute..."):
            try:
                res = requests.post(
                    f"{API_BASE}/optimize",
                    json={
                        "jd_text": jd_text,
                        "target_score": target_score,
                        "max_iterations": max_iterations,
                    },
                )
                res.raise_for_status()
                st.session_state["result"] = res.json()
            except Exception as e:
                st.error(f"Optimization failed: {e}")
                st.session_state["result"] = None

if st.session_state.get("result"):
    result = st.session_state["result"]

    st.subheader("Result")

    status_labels = {
        "success": ("✅ Success", "success"),
        "plateaued": ("⚠️ Plateaued", "warning"),
        "max_iterations_reached": ("⚠️ Max iterations reached", "warning"),
    }
    label, kind = status_labels.get(result["status"], (result["status"], "info"))

    m1, m2, m3 = st.columns(3)
    m1.metric("Final score", f"{result['final_score']} / 100")
    m2.metric("Iterations run", result["iterations_run"])
    m3.metric("Status", label)

    st.line_chart(result["score_history"])

    if result["genuine_gaps"]:
        st.markdown("**Honest gaps this loop couldn't close by rephrasing:**")
        for gap in result["genuine_gaps"]:
            st.markdown(f"- {gap}")

    pdf_res = requests.get(f"{API_BASE}/download/{result['pdf_filename']}")
    if pdf_res.ok:
        st.download_button(
            label="Download tailored resume (PDF)",
            data=pdf_res.content,
            file_name=result["pdf_filename"],
            mime="application/pdf",
            use_container_width=True,
        )

st.divider()

# ---------- Step 3: Automatic job discovery ----------
st.subheader("Step 3 — Or, find jobs automatically")
st.caption("Scans RemoteOK, Himalayas, and Remotive for roles matching your resume, "
           "scores every match, and fully tailors resumes for the ones that clear "
           "your target score.")

max_jobs_to_scan = st.slider("How many jobs to scan", min_value=5, max_value=100, value=25)

discover_clicked = st.button("Find jobs & auto-tailor", use_container_width=True)

if discover_clicked:
    with st.spinner("Detecting your domain, searching job boards, and scoring matches "
                     "- this can take a few minutes..."):
        try:
            res = requests.post(
                f"{API_BASE}/discover-and-optimize",
                json={"max_jobs_to_scan": max_jobs_to_scan, "target_score": float(target_score)},
                timeout=600,
            )
            res.raise_for_status()
            st.session_state["discovery_results"] = res.json()["results"]
        except Exception as e:
            st.error(f"Discovery failed: {e}")
            st.session_state["discovery_results"] = None

if st.session_state.get("discovery_results"):
    disc_results = st.session_state["discovery_results"]
    tailored = [r for r in disc_results if r.get("tailored")]

    st.markdown(f"**Scanned {len(disc_results)} jobs — {len(tailored)} fully tailored (93+ score)**")

    if any(r.get("note") for r in disc_results):
        st.warning("Groq's daily quota was reached partway through - results below are partial. "
                    "Try again after the quota resets to scan more.")

    for r in sorted(disc_results, key=lambda x: x.get("quick_score") or 0, reverse=True):
        with st.container(border=True):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{r['title']}** — {r['company']}")
                meta_bits = []
                if r.get("source"):
                    meta_bits.append(r["source"])
                if r.get("location"):
                    meta_bits.append(r["location"])
                if meta_bits:
                    st.caption(" · ".join(meta_bits))
                if r.get("url"):
                    st.caption(r["url"])
            with col2:
                if r.get("quick_score") is not None:
                    st.metric("Quick score", r["quick_score"])

            if r.get("error"):
                st.caption(f"⚠️ {r['error']}")
            elif r.get("note"):
                st.caption(f"⚠️ {r['note']}")
            elif r.get("tailored"):
                st.success(f"Tailored to {r['final_score']} / 100")
                pdf_res = requests.get(f"{API_BASE}/download/{r['pdf_filename']}")
                if pdf_res.ok:
                    st.download_button(
                        label="Download tailored PDF",
                        data=pdf_res.content,
                        file_name=r["pdf_filename"],
                        mime="application/pdf",
                        key=r["pdf_filename"],
                    )
            elif r.get("final_score") is not None:
                st.caption(f"Tailored attempt reached {r['final_score']} - below target, not saved as final PDF")