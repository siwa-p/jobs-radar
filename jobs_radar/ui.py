from pathlib import Path

import httpx
import pandas as pd
import streamlit as st

from jobs_radar.config import settings

BASE = settings.api_base

st.set_page_config(page_title="Jobs Radar", layout="wide")
st.title("Jobs Radar")

if "parsed_resume" not in st.session_state:
    st.session_state.parsed_resume = None
if "search_results" not in st.session_state:
    st.session_state.search_results = []
if "llm_enabled" not in st.session_state:
    try:
        r = httpx.get(f"{BASE}/health", timeout=5)
        st.session_state.llm_enabled = r.json().get("llm_enabled", False)
    except Exception:
        st.session_state.llm_enabled = False

llm_enabled = st.session_state.llm_enabled

tab1, tab2, tab3 = st.tabs(["Resume", "Search Jobs", "Recent Jobs"])


# --- Tab 1: Resume ---
with tab1:
    if llm_enabled:
        model = st.selectbox("Model", ["gpt-4o-mini", "gpt-4o"], key="parse_model")
        resume_text = st.text_area("Paste your resume", height=300)

        if st.button("Parse", type="primary"):
            if not resume_text.strip():
                st.error("Paste your resume first.")
            else:
                with st.spinner("Parsing..."):
                    try:
                        r = httpx.post(
                            f"{BASE}/parse",
                            json={"resume_text": resume_text, "model": model},
                            timeout=30,
                        )
                        r.raise_for_status()
                        data = r.json()
                        st.session_state.parsed_resume = data["parsed_resume"]
                        st.success(f"Parsed in {data['parsing_time_seconds']}s using {data['model_used']}")
                        st.json(data["parsed_resume"])
                    except Exception as e:
                        st.error(f"Error: {e}")
    else:
        st.info("No OpenAI key configured — enter your target roles and skills manually.")
        roles_raw = st.text_input("Target roles (comma-separated)", "backend engineer, data engineer")
        skills_raw = st.text_input("Core skills (comma-separated)", "Python, SQL, AWS")

        if st.button("Save", type="primary"):
            roles = [r.strip() for r in roles_raw.split(",") if r.strip()]
            skills = [s.strip() for s in skills_raw.split(",") if s.strip()]
            if not roles:
                st.error("Enter at least one target role.")
            else:
                st.session_state.parsed_resume = {
                    "target_roles": roles,
                    "core_skills": skills,
                    "excluded_roles": [],
                    "seniority": [],
                    "years_experience": None,
                    "education_level": None,
                    "summary": None,
                }
                st.success(f"Saved: {', '.join(roles)}")


# --- Tab 2: Search Jobs ---
with tab2:
    if not st.session_state.parsed_resume:
        st.info("Fill in your resume in tab 1 first.")
    else:
        st.write(f"Resume loaded: **{', '.join(st.session_state.parsed_resume['target_roles'])}**")

        col1, col2 = st.columns(2)
        with col1:
            queries_raw = st.text_input("Search queries (comma-separated)", "backend engineer, data engineer")
            locations_raw = st.text_input("Locations (comma-separated)", "New York, NY")
            if llm_enabled:
                search_model = st.selectbox("Model", ["gpt-4o-mini", "gpt-4o"], key="search_model")
            else:
                search_model = "gpt-4o-mini"
        with col2:
            hours_old = st.slider("Posted within (hours)", 24, 168, 48)
            top_k = st.slider("Max results", 5, 50, 10)
            entry_level_only = st.checkbox("Entry level only", True)
            remote_only = st.checkbox("Remote only", True)
            exclude_senior = st.checkbox("Exclude senior", True)
            exclude_clearance = st.checkbox("Exclude clearance", True)

        if st.button("Search", type="primary"):
            queries = [q.strip() for q in queries_raw.split(",") if q.strip()]
            locations = [l.strip() for l in locations_raw.split(",") if l.strip()]
            payload = {
                "parsed_resume": st.session_state.parsed_resume if llm_enabled else None,
                "model": search_model,
                "queries": queries,
                "locations": locations,
                "hours_old": hours_old,
                "top_k": top_k,
                "filters": {
                    "entry_level_only": entry_level_only,
                    "remote_only": remote_only,
                    "exclude_senior": exclude_senior,
                    "exclude_clearance": exclude_clearance,
                },
            }
            with st.spinner("Scraping jobs... this may take a minute."):
                try:
                    r = httpx.post(f"{BASE}/search", json=payload, timeout=300)
                    r.raise_for_status()
                    data = r.json()
                    st.session_state.search_results = data["jobs"]
                    st.success(f"Found {data['total_found']} jobs in {data['search_time_seconds']}s — query: {data.get('query_used')}")
                except Exception as e:
                    st.error(f"Error: {e}")

        for i, job in enumerate(st.session_state.search_results):
            score = job.get("relevance_score")
            score_str = f"{score:.3f}" if score is not None else "N/A"
            if llm_enabled:
                rating = job.get("llm_rating") or 0
                header = f"[LLM {rating}/10 | Score {score_str}]  {job['title']} @ {job['company']}"
            else:
                header = f"[Score {score_str}]  {job['title']} @ {job['company']}"

            with st.expander(header):
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.write(f"**Location:** {job.get('location') or 'N/A'}")
                    st.write(f"**Experience:** {job.get('experience_required') or 'N/A'}")
                    st.write(f"**Vector Score:** {score_str}")
                    if llm_enabled:
                        st.write(f"**LLM Rating:** {job.get('llm_rating') or 0}/10")
                        st.write(f"**Reasoning:** {job.get('llm_reasoning') or 'N/A'}")
                    if job.get("job_url"):
                        st.link_button("View Job", job["job_url"])
                with col2:
                    user_rating = st.slider("Your rating (1-5)", 1, 5, 3, key=f"sr_{i}")
                    notes = st.text_input("Notes", key=f"sn_{i}")
                    if st.button("Save feedback", key=f"sf_{i}"):
                        try:
                            fr = httpx.post(
                                f"{BASE}/feedback",
                                json={"job_url": job.get("job_url") or f"unknown_{i}", "user_rating": user_rating, "notes": notes},
                                timeout=10,
                            )
                            fr.raise_for_status()
                            st.success("Saved!")
                        except Exception as e:
                            st.error(f"Error: {e}")


# --- Tab 3: Recent Jobs ---
with tab3:
    if st.button("Load recent jobs"):
        try:
            r = httpx.get(f"{BASE}/results/recent", timeout=10)
            r.raise_for_status()
            jobs = r.json()
            df = pd.DataFrame(jobs)
            cols = ["title", "company", "location", "llm_rating", "relevance_score", "experience_required", "user_rating", "notes", "job_url"]
            display_df = df[[c for c in cols if c in df.columns]].copy()
            if "llm_rating" in display_df.columns:
                display_df["llm_rating"] = display_df["llm_rating"].apply(lambda x: "—" if x is None or (isinstance(x, float) and pd.isna(x)) else x)
            st.dataframe(display_df, use_container_width=True)

            try:
                cr = httpx.get(f"{BASE}/results/correlation", timeout=5)
                if cr.status_code == 200:
                    c = cr.json()
                    st.metric(
                        label=f"LLM vs you — Pearson r (n={c['n']})",
                        value=c["pearson_r"],
                        help="Correlation between LLM ratings and your ratings. Closer to 1.0 means the LLM agrees with you.",
                    )
            except Exception:
                pass

            csvs = sorted(settings.data_dir.glob("jobs_*.csv"), reverse=True)
            if csvs:
                st.download_button(
                    label="Download CSV",
                    data=csvs[0].read_bytes(),
                    file_name=csvs[0].name,
                    mime="text/csv",
                )

            st.divider()
            for i, job in enumerate(jobs):
                llm = job.get("llm_rating")
                score = job.get("relevance_score")
                score_str = f"{score:.3f}" if score is not None else "N/A"
                if llm_enabled and llm is not None:
                    header = f"[LLM {llm}/10 | Score {score_str}]  {job['title']} @ {job['company']}"
                else:
                    header = f"[Score {score_str}]  {job['title']} @ {job['company']}"

                with st.expander(header):
                    col1, col2 = st.columns([2, 1])
                    with col1:
                        st.write(f"**Location:** {job.get('location') or 'N/A'}")
                        st.write(f"**Experience:** {job.get('experience_required') or 'N/A'}")
                        if llm is not None:
                            st.write(f"**Reasoning:** {job.get('llm_reasoning') or 'N/A'}")
                        if job.get("job_url"):
                            st.link_button("View Job", job["job_url"])
                    with col2:
                        default_rating = int(job["user_rating"]) if job.get("user_rating") else 3
                        user_rating = st.slider("Your rating (1-5)", 1, 5, default_rating, key=f"rr_{i}")
                        notes = st.text_input("Notes", value=job.get("notes") or "", key=f"rn_{i}")
                        if st.button("Save", key=f"rf_{i}"):
                            try:
                                fr = httpx.post(
                                    f"{BASE}/feedback",
                                    json={"job_url": job["job_url"], "user_rating": user_rating, "notes": notes},
                                    timeout=10,
                                )
                                fr.raise_for_status()
                                st.success("Saved!")
                            except Exception as e:
                                st.error(f"Error: {e}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                st.info("No results yet — run a search first.")
            else:
                st.error(f"Error: {e}")
