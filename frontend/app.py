import streamlit as st
import requests
import time
import os
from typing import cast
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

# Works locally (.env) AND on Streamlit Cloud (st.secrets)
SUPABASE_URL = os.getenv("SUPABASE_URL") or st.secrets.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY") or st.secrets.get("SUPABASE_ANON_KEY", "")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    st.error("SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env (local) or Secrets (Streamlit Cloud).")
    st.stop()

API_BASE = "http://127.0.0.1:8000"

st.set_page_config(page_title="Resume Optimizer", page_icon="🎯", layout="centered")

supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# ---------- Auth gate ----------
if "access_token" not in st.session_state:
    st.title("🎯 Resume Optimizer")
    st.caption("Sign in to continue")

    tab_login, tab_signup = st.tabs(["Log in", "Sign up"])

    with tab_login:
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        if st.button("Log in", use_container_width=True):
            try:
                res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                if res.session is None or res.user is None:
                    st.error("Login failed: no session returned.")
                else:
                    st.session_state["access_token"] = res.session.access_token
                    st.session_state["user_email"] = res.user.email
                    st.rerun()
            except Exception as e:
                st.error(f"Login failed: {e}")

    with tab_signup:
        new_email = st.text_input("Email", key="signup_email")
        new_password = st.text_input("Password", type="password", key="signup_password")
        if st.button("Sign up", use_container_width=True):
            try:
                supabase.auth.sign_up({"email": new_email, "password": new_password})
                st.success("Account created! Check your email to confirm, then log in.")
            except Exception as e:
                st.error(f"Sign up failed: {e}")

    st.stop()  # nothing below this runs until logged in

# ---------- Logged in - build auth headers for every backend call ----------
AUTH_HEADERS = {"Authorization": f"Bearer {st.session_state['access_token']}"}

with st.sidebar:
    st.caption(f"Logged in as {st.session_state.get('user_email', '')}")
    if st.button("Log out"):
        st.session_state.clear()
        st.rerun()

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
                res = requests.post(f"{API_BASE}/upload-resume", files=files, headers=AUTH_HEADERS)
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

if run_clicked:
    if not jd_text.strip():
        st.warning("Paste a job description first.")
    else:
        with st.spinner("Running the optimization loop - this can take a minute..."):
            try:
                res = requests.post(
                    f"{API_BASE}/optimize",
                    json={"jd_text": jd_text, "target_score": target_score, "max_iterations": max_iterations},
                    headers=AUTH_HEADERS,
                )
                res.raise_for_status()
                st.session_state["result"] = res.json()
            except Exception as e:
                st.error(f"Optimization failed: {e}")
                st.session_state["result"] = None

if st.session_state.get("result"):
    result = st.session_state["result"]
    st.subheader("Result")

    status_display_labels = {
        "success": ("✅ Success", "success"),
        "plateaued": ("⚠️ Plateaued", "warning"),
        "max_iterations_reached": ("⚠️ Max iterations reached", "warning"),
    }
    label, kind = status_display_labels.get(result["status"], (result["status"], "info"))

    m1, m2, m3 = st.columns(3)
    m1.metric("Final score", f"{result['final_score']} / 100")
    m2.metric("Iterations run", result["iterations_run"])
    m3.metric("Status", label)

    st.line_chart(result["score_history"])

    if result["genuine_gaps"]:
        st.markdown("**Honest gaps this loop couldn't close by rephrasing:**")
        for gap in result["genuine_gaps"]:
            st.markdown(f"- {gap}")

    pdf_res = requests.get(f"{API_BASE}/download/{result['pdf_filename']}", headers=AUTH_HEADERS)
    if pdf_res.ok:
        st.download_button(
            label="Download tailored resume (PDF)",
            data=pdf_res.content,
            file_name=result["pdf_filename"],
            mime="application/pdf",
            use_container_width=True,
        )

st.divider()

# ---------- Step 3: Automatic job discovery (LIVE) ----------
st.subheader("Step 3 — Or, find jobs automatically")
st.caption("Scans your configured job platforms, scores every match, and fully "
           "tailors resumes for the ones that clear your target score.")

max_jobs_to_scan = st.slider("How many jobs to scan", min_value=5, max_value=100, value=25)
discover_clicked = st.button("Find jobs & auto-tailor", use_container_width=True)

if discover_clicked:
    try:
        requests.post(
            f"{API_BASE}/start-discovery",
            json={"max_jobs_to_scan": max_jobs_to_scan, "target_score": float(target_score)},
            headers=AUTH_HEADERS,
        )
    except Exception as e:
        st.error(f"Could not start discovery: {e}")

    progress_placeholder = st.empty()
    status_placeholder = st.empty()

    while True:
        try:
            prog = requests.get(f"{API_BASE}/discovery-progress", headers=AUTH_HEADERS).json()
        except Exception as e:
            status_placeholder.error(f"Lost connection to backend: {e}")
            break

        results = prog.get("results", [])
        is_running = prog.get("is_running", False)

        with progress_placeholder.container():
            st.markdown(f"**{len(results)} jobs processed so far...**")
            for r in sorted(results, key=lambda x: x.get("quick_score") or 0, reverse=True):
                with st.container(border=True):
                    st.markdown(f"**{r['title']}** — {r['company']}")
                    if r.get("quick_score") is not None:
                        st.caption(f"Quick score: {r['quick_score']}")
                    if r.get("tailored"):
                        st.success(f"Tailored to {r['final_score']} / 100 ✓")
                    elif r.get("final_score") is not None:
                        st.caption(f"Reached {r['final_score']} - below target")
                    elif r.get("note"):
                        st.caption(f"⚠️ {r['note']}")

        if not is_running:
            status_placeholder.success("Discovery complete! Full details below.")
            st.session_state["discovery_results"] = results
            break

        status_placeholder.info("🔴 Live — still scanning, updating every 5 seconds...")
        time.sleep(5)

if st.session_state.get("discovery_results"):
    disc_results = st.session_state["discovery_results"]
    tailored = [r for r in disc_results if r.get("tailored")]

    st.markdown(f"**{len(disc_results)} jobs processed — {len(tailored)} fully tailored (target score+)**")

    try:
        applied_res = requests.get(f"{API_BASE}/applied-jobs", headers=AUTH_HEADERS)
        applied_list = applied_res.json().get("applied_jobs", []) if applied_res.ok else []
    except Exception:
        applied_list = []
    applied_keys = {(a["title"], a["company"]) for a in applied_list}

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
                pdf_res = requests.get(f"{API_BASE}/download/{r['pdf_filename']}", headers=AUTH_HEADERS)
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

            already_applied = (r["title"], r["company"]) in applied_keys
            checkbox_key = f"applied_{r['title']}_{r['company']}"
            applied_checked = st.checkbox("Applied to this job", value=already_applied, key=checkbox_key)

            if applied_checked and not already_applied:
                requests.post(f"{API_BASE}/mark-applied", json={
                    "title": r["title"], "company": r["company"],
                    "url": r.get("url", ""), "source": r.get("source", ""),
                    "ats_score": r.get("final_score") or r.get("quick_score"),
                }, headers=AUTH_HEADERS)
                st.rerun()
            elif not applied_checked and already_applied:
                requests.post(f"{API_BASE}/unmark-applied", json={
                    "title": r["title"], "company": r["company"], "url": "", "source": "",
                }, headers=AUTH_HEADERS)
                st.rerun()

st.divider()

# ---------- Personal Experiment Tracker ----------
st.subheader("📊 One-Month Experiment")
st.caption("Track whether tailored applications actually lead to interview calls.")

summary_res = requests.get(f"{API_BASE}/experiment-summary", params={"days": 30}, headers=AUTH_HEADERS)
if summary_res.ok:
    s = summary_res.json()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Applied (30d)", s["total_applied"])
    c2.metric("Interviews", s["interviews"], delta="Goal: 5" if s["interviews"] < 5 else "Goal met ✅")
    c3.metric("Rejected", s["rejected"])
    c4.metric("Response rate", f"{s['response_rate']}%")

st.divider()
st.subheader("Application History")

status_labels: dict[str, str] = {
    "applied": "📤 Applied",
    "interview_scheduled": "🎯 Interview!",
    "rejected": "❌ Rejected",
    "no_response": "🔇 No response",
    "offer": "🎉 Offer",
}


def _status_label(x: str) -> str:
    return cast(str, status_labels[x])


history_res = requests.get(f"{API_BASE}/applied-jobs", headers=AUTH_HEADERS)
if history_res.ok:
    applied = history_res.json().get("applied_jobs", [])
    if not applied:
        st.caption("No jobs marked as applied yet.")
    else:
        for job in applied:
            with st.container(border=True):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(f"**{job['title']}** — {job['company']}")
                    if job.get("source"):
                        st.caption(job["source"])
                    if job.get("ats_score"):
                        st.caption(f"ATS score at time of applying: {job['ats_score']}")
                with col2:
                    st.caption(f"Applied: {job['date_applied']}")

                current_status = job.get("status", "applied")
                new_status = st.selectbox(
                    "Status",
                    options=list(status_labels.keys()),
                    format_func=_status_label,
                    index=list(status_labels.keys()).index(current_status),
                    key=f"status_{job['title']}_{job['company']}",
                )
                if new_status != current_status:
                    requests.post(f"{API_BASE}/update-application-status", json={
                        "title": job["title"], "company": job["company"], "status": new_status,
                    }, headers=AUTH_HEADERS)
                    st.rerun()
else:
    st.caption("Could not load application history - is the backend running?")