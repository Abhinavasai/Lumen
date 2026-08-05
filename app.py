"""
app.py — Job Hunter Streamlit UI
Run: python -m streamlit run app.py
"""
import json
import os
import re
import sqlite3
import subprocess
import sys
import yaml
import streamlit as st
from dotenv import load_dotenv
from openai import AzureOpenAI
from datetime import datetime

BASE_DIR           = os.path.dirname(os.path.abspath(__file__))
DB_PATH            = os.path.join(BASE_DIR, "db", "jobs.db")
CONFIG_PATH        = os.path.join(BASE_DIR, "config.yaml")
FILTERED_JOBS_PATH = os.path.join(BASE_DIR, "output", "top25_jobs.json")

load_dotenv(os.path.join(BASE_DIR, ".env"))

st.set_page_config(
    page_title="Job Hunter",
    page_icon="briefcase",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Theme ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Base & background ── */
html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
    background-color: #f5f0e8 !important;
    font-family: 'Inter', 'Segoe UI', sans-serif;
    color: #2c2c2c;
}
[data-testid="stSidebar"] {
    background-color: #ede8df !important;
    border-right: 1px solid #d9d2c5;
}
[data-testid="stSidebar"] * {
    color: #1a1a1a !important;
}
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] div {
    color: #1a1a1a !important;
}
[data-testid="stSidebar"] input,
[data-testid="stSidebar"] textarea {
    color: #1a1a1a !important;
    background: #fffdf8 !important;
    border: 1px solid #c8bfb0 !important;
    border-radius: 8px !important;
}
[data-testid="stSidebar"] [data-testid="stButton"] > button {
    color: #1a1a1a !important;
    background: #fff9f0 !important;
    border: 1px solid #c8bfb0 !important;
}
[data-testid="stSidebar"] [data-testid="stButton"] > button[kind="primary"] {
    background: #4a3f35 !important;
    color: #fff9f0 !important;
    border-color: #4a3f35 !important;
}

/* ── Sidebar header ── */
.sidebar-header {
    font-size: 1.2rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    color: #4a3f35;
    margin-bottom: 1.2rem;
    padding-bottom: 0.5rem;
    border-bottom: 2px solid #c8bfb0;
}

/* ── Page title ── */
.page-title {
    font-size: 1.8rem;
    font-weight: 700;
    color: #3b3028;
    letter-spacing: 0.02em;
    margin-bottom: 0.2rem;
}
.page-subtitle {
    font-size: 0.9rem;
    color: #8a7f74;
    margin-bottom: 1.5rem;
}

/* ── Stat cards ── */
.stat-card {
    background: #fff9f0;
    border: 1px solid #ddd5c6;
    border-radius: 10px;
    padding: 1rem 1.2rem;
    text-align: center;
}
.stat-number { font-size: 1.6rem; font-weight: 700; color: #4a3f35; }
.stat-label  { font-size: 0.78rem; color: #8a7f74; text-transform: uppercase; letter-spacing: 0.06em; }

/* ── Job card ── */
.job-card {
    background: #fffdf8;
    border: 1px solid #ddd5c6;
    border-radius: 12px;
    padding: 1.1rem 1.3rem;
    margin-bottom: 0.7rem;
    transition: box-shadow 0.15s;
}
.job-card:hover { box-shadow: 0 3px 12px rgba(0,0,0,0.08); }

.job-title    { font-size: 1.0rem; font-weight: 600; color: #3b3028; }
.job-company  { font-size: 0.88rem; color: #6b5e52; margin-top: 0.1rem; }
.job-meta     { font-size: 0.78rem; color: #9a8f83; margin-top: 0.35rem; }

.score-pill {
    display: inline-block;
    padding: 0.18rem 0.7rem;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 600;
    margin-right: 0.5rem;
}
.score-high   { background: #d4edda; color: #276d38; }
.score-mid    { background: #fff3cd; color: #856404; }
.score-low    { background: #f8d7da; color: #842029; }

.source-tag {
    display: inline-block;
    background: #ede8df;
    color: #6b5e52;
    border-radius: 6px;
    padding: 0.1rem 0.5rem;
    font-size: 0.72rem;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

.reason-box {
    background: #f5f0e8;
    border-left: 3px solid #c8bfb0;
    border-radius: 0 6px 6px 0;
    padding: 0.5rem 0.8rem;
    font-size: 0.83rem;
    color: #5a4f44;
    margin-top: 0.5rem;
}

/* ── Buttons ── */
[data-testid="stButton"] > button {
    border-radius: 8px !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
    border: 1px solid #c8bfb0 !important;
    background: #fff9f0 !important;
    color: #2c2c2c !important;
    box-shadow: none !important;
    transition: background 0.15s, border-color 0.15s !important;
}
[data-testid="stButton"] > button:hover,
[data-testid="stButton"] > button:focus,
[data-testid="stButton"] > button:active {
    background: #ede8df !important;
    border-color: #a89887 !important;
    color: #2c2c2c !important;
    box-shadow: none !important;
}

/* ── Primary (Run pipeline) ── */
[data-testid="stButton"] > button[kind="primary"],
[data-testid="stButton"] > button[kind="primary"]:hover,
[data-testid="stButton"] > button[kind="primary"]:focus,
[data-testid="stButton"] > button[kind="primary"]:active {
    background: #c8a97e !important;
    color: #1a1a1a !important;
    border-color: #b8965c !important;
    font-weight: 600 !important;
}
[data-testid="stButton"] > button[kind="primary"]:hover {
    background: #b8965c !important;
}

/* ── Align action buttons flush with the expander header row ── */
div[data-testid="column"]:has(button[title="Open link and build tailored resume"]),
div[data-testid="column"]:has(button[title="Remove and never show again"]) {
    display: flex;
    align-items: flex-start;
    padding-top: 0 !important;
}
div[data-testid="column"]:has(button[title="Open link and build tailored resume"]) > div[data-testid="stVerticalBlock"],
div[data-testid="column"]:has(button[title="Remove and never show again"]) > div[data-testid="stVerticalBlock"] {
    padding-top: 0 !important;
    gap: 0 !important;
}
div[data-testid="column"]:has(button[title="Open link and build tailored resume"]) [data-testid="stButton"],
div[data-testid="column"]:has(button[title="Remove and never show again"]) [data-testid="stButton"] {
    margin-top: 0.25rem;
}

/* ── Apply (↗) — green tint ── */
[data-testid="stButton"]:has(button[title="Open link and build tailored resume"]) button {
    background: #edf5ea !important;
    border-color: #aecba8 !important;
    color: #1a3318 !important;
}
[data-testid="stButton"]:has(button[title="Open link and build tailored resume"]) button:hover {
    background: #ddecd9 !important;
}

/* ── Remove (✕) — warm tint ── */
[data-testid="stButton"]:has(button[title="Remove and never show again"]) button {
    background: #fdf0f0 !important;
    border-color: #e8c4c4 !important;
    color: #5a1a1a !important;
}
[data-testid="stButton"]:has(button[title="Remove and never show again"]) button:hover {
    background: #f5e0e0 !important;
}

/* ── Tabs ── */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    background: transparent;
    border-bottom: 2px solid #d9d2c5;
    gap: 0.5rem;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    font-size: 0.88rem !important;
    font-weight: 500 !important;
    color: #8a7f74 !important;
    background: transparent !important;
    border: none !important;
    padding: 0.5rem 1.1rem !important;
    border-radius: 6px 6px 0 0 !important;
}
[data-testid="stTabs"] [aria-selected="true"] {
    color: #3b3028 !important;
    font-weight: 700 !important;
    border-bottom: 2px solid #4a3f35 !important;
}

/* ── Inputs ── */
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea {
    background: #fffdf8 !important;
    border: 1px solid #c8bfb0 !important;
    border-radius: 8px !important;
    color: #1a1a1a !important;
    font-size: 0.85rem !important;
}
[data-testid="stTextInput"] label,
[data-testid="stTextArea"] label,
[data-testid="stSlider"] label,
[data-testid="stSelectSlider"] label {
    color: #1a1a1a !important;
}
[data-testid="stSlider"] { accent-color: #4a3f35; }

/* ── Dividers ── */
hr { border-color: #d9d2c5 !important; }

/* ── Metrics ── */
[data-testid="stMetric"] {
    background: #fff9f0;
    border: 1px solid #ddd5c6;
    border-radius: 10px;
    padding: 0.8rem 1rem;
}
[data-testid="stMetricLabel"] { color: #8a7f74 !important; font-size: 0.78rem !important; }
[data-testid="stMetricValue"] { color: #3b3028 !important; font-weight: 700 !important; }

/* ── Expander ── */
[data-testid="stExpander"] {
    background: #fffdf8 !important;
    border: 1px solid #ddd5c6 !important;
    border-radius: 10px !important;
}
[data-testid="stExpanderToggleIcon"] { color: #6b5e52 !important; }

/* ── Info / success / warning boxes ── */
[data-testid="stAlert"] {
    border-radius: 8px !important;
    font-size: 0.85rem !important;
}

/* ── Applied table header ── */
.table-header {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: #8a7f74;
    font-weight: 600;
    padding-bottom: 0.3rem;
}
.table-row {
    padding: 0.5rem 0;
    border-bottom: 1px solid #ede8df;
    font-size: 0.85rem;
    color: #3b3028;
}
</style>
""", unsafe_allow_html=True)


# ─── Data helpers ─────────────────────────────────────────────────────────────

def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_config(config: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)


def _ensure_applied_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS applied_jobs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            source_job_id   TEXT UNIQUE,
            title           TEXT,
            company         TEXT,
            url             TEXT,
            applied_at      TEXT
        )
    """)


def dismiss_job(job: dict):
    if not os.path.exists(DB_PATH):
        return
    conn = sqlite3.connect(DB_PATH)
    # Ensure dismissed column exists (migrate older databases)
    existing = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    if "dismissed" not in existing:
        conn.execute("ALTER TABLE jobs ADD COLUMN dismissed INTEGER DEFAULT 0")
    conn.execute("UPDATE jobs SET dismissed = 1 WHERE url = ?", (job.get("url", ""),))
    conn.commit()
    conn.close()


def mark_applied(jobs: list[dict]):
    if not os.path.exists(DB_PATH):
        return
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    _ensure_applied_table(conn)
    for job in jobs:
        conn.execute(
            "INSERT OR IGNORE INTO applied_jobs (source_job_id, title, company, url, applied_at) VALUES (?,?,?,?,?)",
            (job.get("source_job_id",""), job.get("title",""), job.get("company",""), job.get("url",""), now),
        )
    conn.commit()
    conn.close()


def get_applied_count() -> int:
    if not os.path.exists(DB_PATH):
        return 0
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT COUNT(*) FROM applied_jobs").fetchone()
        conn.close()
        return row[0] if row else 0
    except Exception:
        return 0


def get_auto_apply_summary() -> dict:
    """Return counts by status: {submitted: N, failed: N, error: N, dry_run: N, total: N}."""
    result = {"submitted": 0, "failed": 0, "error": 0, "dry_run": 0, "total": 0}
    if not os.path.exists(DB_PATH):
        return result
    try:
        conn = sqlite3.connect(DB_PATH)
        existing = {row[1] for row in conn.execute("PRAGMA table_info(applied_jobs)").fetchall()}
        if "status" not in existing:
            conn.close()
            return result
        rows = conn.execute("SELECT status, COUNT(*) FROM applied_jobs GROUP BY status").fetchall()
        conn.close()
        for status, cnt in rows:
            if status in result:
                result[status] = cnt
            result["total"] += cnt
        return result
    except Exception:
        return result


def get_applied_jobs() -> list[dict]:
    if not os.path.exists(DB_PATH):
        return []
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        existing = {row[1] for row in conn.execute("PRAGMA table_info(applied_jobs)").fetchall()}
        has_status = "status" in existing and "platform" in existing and "error" in existing
        if has_status:
            rows = conn.execute(
                "SELECT source_job_id, title, company, url, applied_at, platform, status, error "
                "FROM applied_jobs ORDER BY applied_at DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT source_job_id, title, company, url, applied_at FROM applied_jobs ORDER BY applied_at DESC"
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_jobs(top_n: int | None = None) -> list[dict]:
    if not os.path.exists(DB_PATH):
        return []
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        # Check if new columns exist for proper filtering
        existing = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        has_new_cols = "is_top_pick" in existing and "dismissed" in existing

        if top_n:
            if has_new_cols:
                rows = conn.execute("""
                    SELECT * FROM jobs
                    WHERE run_date = (SELECT MAX(run_date) FROM jobs)
                      AND is_top_pick = 1
                      AND dismissed = 0
                    ORDER BY ai_score DESC
                """).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM jobs
                    WHERE run_date = (SELECT MAX(run_date) FROM jobs)
                      AND ai_score IS NOT NULL
                    ORDER BY ai_score DESC LIMIT ?
                """, (top_n,)).fetchall()
        else:
            if has_new_cols:
                rows = conn.execute("""
                    SELECT * FROM jobs
                    WHERE run_date = (SELECT MAX(run_date) FROM jobs)
                      AND dismissed = 0
                    ORDER BY COALESCE(ai_score, 0) DESC
                """).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM jobs
                    WHERE run_date = (SELECT MAX(run_date) FROM jobs)
                    ORDER BY COALESCE(ai_score, 0) DESC
                """).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_last_run() -> str:
    if not os.path.exists(DB_PATH):
        return "Never"
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT MAX(run_date) FROM jobs").fetchone()
        conn.close()
        return row[0] if row and row[0] else "Never"
    except Exception:
        return "Never"


def clear_jobs_db():
    if not os.path.exists(DB_PATH):
        return
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM jobs")
        conn.commit()
        conn.close()
    except Exception:
        pass


def find_job_index_in_filtered(url: str) -> int | None:
    if not os.path.exists(FILTERED_JOBS_PATH):
        return None
    try:
        with open(FILTERED_JOBS_PATH, encoding="utf-8") as f:
            jobs = json.load(f)
        for i, job in enumerate(jobs):
            if job.get("url") == url:
                return i
    except Exception:
        pass
    return None


def build_resume_background(job_index: int):
    subprocess.Popen(
        [sys.executable, os.path.join(BASE_DIR, "src", "build_all_resumes.py"), "--job", str(job_index)],
        cwd=BASE_DIR,
        creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0,
    )


def run_pipeline_background():
    clear_jobs_db()
    subprocess.Popen(
        [sys.executable, os.path.join(BASE_DIR, "src", "run_pipeline.py"), "--fetch-only"],
        cwd=BASE_DIR,
        creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0,
    )


def build_resumes_background():
    subprocess.Popen(
        [sys.executable, os.path.join(BASE_DIR, "src", "build_all_resumes.py"), "--reset"],
        cwd=BASE_DIR,
        creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0,
    )


def auto_apply_background(dry_run: bool = False, source: str | None = None):
    cmd = [sys.executable, os.path.join(BASE_DIR, "src", "auto_apply.py")]
    if dry_run:
        cmd.append("--dry-run")
    if source:
        cmd.extend(["--source", source])
    subprocess.Popen(
        cmd,
        cwd=BASE_DIR,
        creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0,
    )


# ─── Job card renderer ───────────────────────────────────────────────────────

def score_pill(score) -> str:
    if score is None:
        return ""
    cls = "score-high" if score >= 8 else ("score-mid" if score >= 6 else "score-low")
    return f'<span class="score-pill {cls}">{score}/10</span>'


def render_job_card(job: dict, show_score: bool = True):
    score  = job.get("ai_score")
    pill   = score_pill(score) if show_score else ""
    src    = job.get("source", "")
    posted = (job.get("posted_at") or "N/A")[:10]
    loc    = job.get("location", "N/A")

    header_html = f"""
    <div class="job-card">
        <div class="job-title">{pill}{job.get('title','')}</div>
        <div class="job-company">{job.get('company','')} &nbsp;·&nbsp; {loc}</div>
        <div class="job-meta">
            <span class="source-tag">{src}</span>
            &nbsp; Posted: {posted}
        </div>
        {f'<div class="reason-box">{job["ai_reason"]}</div>' if show_score and job.get("ai_reason") else ""}
    </div>
    """

    with st.expander(f"{job.get('title','')}  ·  {job.get('company','')}"):
        st.markdown(header_html, unsafe_allow_html=True)
        if job.get("url"):
            st.markdown(f"[Open job posting →]({job['url']})")
        if job.get("description"):
            with st.expander("View full description"):
                st.text(job["description"][:3000])


# ─── AI extraction helper ────────────────────────────────────────────────────

def get_azure_client():
    cfg = load_config().get("azure_openai", {})
    return AzureOpenAI(
        azure_endpoint=cfg["endpoint"],
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version="2025-03-01-preview",
    ), cfg["deployment"]


def extract_job_fields(description: str) -> dict:
    """Call Azure OpenAI to extract title, company, location, url from a raw JD."""
    try:
        client, deployment = get_azure_client()
        prompt = (
            "Extract the following fields from this job description. "
            "Return ONLY a JSON object with keys: title, company, location, url. "
            "If a field is not found, use an empty string.\n\n"
            f"Job Description:\n{description[:4000]}"
        )
        resp = client.responses.create(model=deployment, input=prompt)
        text = (resp.output_text or "").strip()
        match = re.search(r"\{.*?\}", text, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return {
                "title":    str(data.get("title",    "")).strip(),
                "company":  str(data.get("company",  "")).strip(),
                "location": str(data.get("location", "")).strip(),
                "url":      str(data.get("url",      "")).strip(),
            }
    except Exception as e:
        return {"_error": str(e), "title": "", "company": "", "location": "", "url": ""}
    return {"title": "", "company": "", "location": "", "url": ""}


# ─── Sidebar ─────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown('<div class="sidebar-header">Configuration</div>', unsafe_allow_html=True)

    config = load_config()

    keywords_str = st.text_area(
        "Job keywords  (one per line)",
        value="\n".join(config.get("keywords", [])),
        height=170,
    )
    max_results = st.slider(
        "Max jobs to fetch",
        min_value=10, max_value=1000,
        value=config["filters"]["max_results"],
        step=10,
    )
    location = st.text_input(
        "Location",
        value=config["filters"].get("location", "United States"),
    )
    posted_within_hours = st.select_slider(
        "Posted within",
        options=[6, 12, 24, 48, 72, 168],
        value=config["filters"].get("posted_within_hours", 24),
        format_func=lambda h: f"{h} hrs" if h < 168 else "7 days",
    )
    top_n = st.slider(
        "AI top picks",
        min_value=5, max_value=50,
        value=config["ai_ranking"]["top_n"],
        step=5,
    )
    min_score = st.slider(
        "Minimum AI score",
        min_value=1, max_value=8,
        value=config["ai_ranking"].get("min_score", 5),
        step=1,
        help="Jobs scoring below this are excluded from Top Picks, even if the pool is small.",
    )

    if st.button("Save settings", use_container_width=True):
        config["keywords"] = [k.strip() for k in keywords_str.strip().splitlines() if k.strip()]
        config["filters"]["max_results"] = max_results
        config["filters"]["location"] = location
        config["filters"]["posted_within_hours"] = posted_within_hours
        config["ai_ranking"]["top_n"] = top_n
        config["ai_ranking"]["min_score"] = min_score
        save_config(config)
        st.success("Settings saved.")

    st.divider()

    last_run = get_last_run()
    applied_total = get_applied_count()
    st.caption(f"Last run: **{last_run}**")
    if applied_total:
        st.caption(f"Applied so far: **{applied_total}** jobs")

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Run pipeline", type="primary", use_container_width=True):
        run_pipeline_background()
        st.info("Pipeline started. Refresh in ~2–3 minutes.")

    if st.button("Refresh results", use_container_width=True):
        st.rerun()

    if st.button("Build all resumes", use_container_width=True):
        build_resumes_background()
        st.info("Resume builder started. Check the terminal window for progress.")

    st.divider()
    st.markdown('<div style="font-size:0.82rem;font-weight:600;color:#4a3f35;margin-bottom:0.5rem;">Auto Apply</div>', unsafe_allow_html=True)
    apply_source = st.selectbox(
        "Platform",
        options=["All", "greenhouse", "ashby", "lever", "workday", "smartrecruiters", "workable", "bamboohr"],
        index=0,
        label_visibility="collapsed",
    )
    col_apply, col_dry = st.columns(2)
    with col_apply:
        if st.button("Apply Now", type="primary", use_container_width=True):
            src = None if apply_source == "All" else apply_source
            auto_apply_background(dry_run=False, source=src)
            st.info("Auto-apply started. Check the terminal window for progress.")
    with col_dry:
        if st.button("Dry Run", use_container_width=True):
            src = None if apply_source == "All" else apply_source
            auto_apply_background(dry_run=True, source=src)
            st.info("Dry run started. Check the terminal window to preview.")

    progress_file = os.path.join(BASE_DIR, "output", "auto_apply_progress.json")
    if os.path.exists(progress_file):
        try:
            with open(progress_file, encoding="utf-8") as _pf:
                aa_progress = json.load(_pf)
        except Exception:
            aa_progress = None

        if aa_progress and aa_progress.get("total", 0) > 0:
            is_running = aa_progress.get("running", False)
            current = aa_progress.get("current", 0)
            total = aa_progress.get("total", 1)
            cur_job = aa_progress.get("current_job")
            n_applied = aa_progress.get("applied", 0)
            n_failed = aa_progress.get("failed", 0)
            n_skipped = aa_progress.get("skipped", 0)

            if is_running:
                st.progress(current / total, text=f"Applying {current}/{total}")
                if cur_job:
                    st.caption(f"Current: **{cur_job['title']}** @ {cur_job['company']} [{cur_job['source']}]")
                st.caption(f"Sent: {n_applied} · Failed: {n_failed} · Skipped: {n_skipped}")
            else:
                failed_tag = f" · <span style='color:#842029;'>{n_failed} failed</span>" if n_failed > 0 else ""
                st.markdown(
                    f'<div style="background:#fff9f0;border:1px solid #ddd5c6;border-radius:8px;'
                    f'padding:0.6rem 0.8rem;margin-top:0.5rem;font-size:0.8rem;">'
                    f'<span style="color:#4a3f35;font-weight:600;">{total}</span> processed '
                    f'&nbsp;·&nbsp; '
                    f'<span style="color:#276d38;">{n_applied} sent</span>'
                    f'{failed_tag}'
                    f'</div>',
                    unsafe_allow_html=True,
                )


# ─── Main panel ──────────────────────────────────────────────────────────────

st.markdown('<div class="page-title">Job Hunter</div>', unsafe_allow_html=True)
st.markdown(f'<div class="page-subtitle">Last pipeline run: {last_run}</div>', unsafe_allow_html=True)

tab_top, tab_all, tab_applied, tab_custom, tab_setup = st.tabs(["AI Top Picks", "All Jobs", "Applied", "Generate Resume", "Setup"])

# ── Tab 1 : AI Top Picks ────────────────────────────────────────────────────
with tab_top:
    top_jobs = get_jobs(top_n=config["ai_ranking"]["top_n"])

    if not top_jobs:
        st.info("No ranked jobs yet. Run the pipeline using the sidebar button.")
    else:
        scores = [j["ai_score"] for j in top_jobs if j.get("ai_score")]
        if scores:
            c1, c2, c3 = st.columns(3)
            c1.metric("Showing", len(top_jobs))
            c2.metric("Avg score", f"{sum(scores)/len(scores):.1f} / 10")
            c3.metric("Top score", f"{max(scores)} / 10")

        st.markdown("<br>", unsafe_allow_html=True)

        # Bulk open all
        urls = [j["url"] for j in top_jobs if j.get("url")]
        if urls and st.button(f"Open all {len(urls)} jobs in new tabs", use_container_width=True):
            mark_applied(top_jobs)
            opens = "\n".join(f'window.top.open("{u}", "_blank");' for u in urls)
            st.components.v1.html(f"<script>{opens}</script>", height=0)
            st.success(f"Marked {len(top_jobs)} jobs as applied.")

        st.divider()

        for job in top_jobs:
            col_card, col_apply, col_dismiss = st.columns([11, 0.7, 0.7])

            with col_card:
                render_job_card(job, show_score=True)

            job_key = job.get("url", str(job.get("id", "")))

            with col_apply:
                if st.button("↗", key=f"apply_{job_key}", help="Open link and build tailored resume"):
                    mark_applied([job])
                    if job.get("url"):
                        st.components.v1.html(
                            f'<script>window.top.open("{job["url"]}", "_blank");</script>',
                            height=0,
                        )
                    idx = find_job_index_in_filtered(job.get("url", ""))
                    if idx is not None:
                        build_resume_background(idx)
                        st.toast(f"Building resume for {job.get('title')} @ {job.get('company')} — check resumes/ when done.")
                    else:
                        st.toast("Link opened. Resume not built — job not found in filtered list.")
                    st.rerun()

            with col_dismiss:
                if st.button("✕", key=f"dismiss_{job_key}", help="Remove and never show again"):
                    dismiss_job(job)
                    st.rerun()


# ── Tab 2 : All Jobs ─────────────────────────────────────────────────────────
with tab_all:
    all_jobs = get_jobs()

    if not all_jobs:
        st.info("No jobs fetched yet. Run the pipeline first.")
    else:
        sources: dict[str, int] = {}
        for j in all_jobs:
            s = j.get("source", "unknown")
            sources[s] = sources.get(s, 0) + 1

        cols = st.columns(len(sources))
        for col, (src, cnt) in zip(cols, sources.items()):
            col.metric(src.capitalize(), cnt)

        st.divider()

        search = st.text_input("Search by title or company", placeholder="e.g. AI engineer, Stripe")
        display = all_jobs
        if search:
            s = search.lower()
            display = [j for j in all_jobs if s in j.get("title","").lower() or s in j.get("company","").lower()]

        st.caption(f"{len(display)} job(s) shown")

        for job in display:
            render_job_card(job, show_score=bool(job.get("ai_score")))


# ── Tab 3 : Applied ──────────────────────────────────────────────────────────
with tab_applied:
    applied = get_applied_jobs()

    if not applied:
        st.info("No applied jobs yet. Click Apply on any job in the Top Picks tab, or run Auto Apply.")
    else:
        has_status_col = "status" in applied[0]

        if has_status_col:
            submitted = [j for j in applied if j.get("status") == "submitted"]
            failed = [j for j in applied if j.get("status") in ("failed", "error")]
            dry_runs = [j for j in applied if j.get("status") == "dry_run"]
            other = [j for j in applied if j.get("status") not in ("submitted", "failed", "error", "dry_run")]

            cs1, cs2, cs3, cs4 = st.columns(4)
            cs1.metric("Total", len(applied))
            cs2.metric("Submitted", len(submitted))
            cs3.metric("Failed", len(failed))
            cs4.metric("Dry Runs", len(dry_runs))

            status_filter = st.selectbox(
                "Filter by status",
                options=["All", "Failed (apply manually)", "Submitted", "Dry Run"],
                index=0,
                label_visibility="collapsed",
            )
            if status_filter == "Failed (apply manually)":
                display_applied = failed
            elif status_filter == "Submitted":
                display_applied = submitted
            elif status_filter == "Dry Run":
                display_applied = dry_runs
            else:
                display_applied = applied

            if failed and status_filter in ("All", "Failed (apply manually)"):
                st.markdown(
                    '<div style="background:#fdf0f0;border:1px solid #e8c4c4;border-radius:10px;'
                    'padding:0.8rem 1.1rem;margin-bottom:0.8rem;">'
                    f'<span style="font-weight:600;color:#842029;">'
                    f'{len(failed)} job(s) failed auto-apply</span>'
                    ' — click the link to apply manually'
                    '</div>',
                    unsafe_allow_html=True,
                )
        else:
            display_applied = applied

        st.divider()

        for job in display_applied:
            status = job.get("status", "submitted") if has_status_col else "submitted"
            platform = job.get("platform", "") if has_status_col else ""
            error_msg = job.get("error", "") if has_status_col else ""

            if status in ("failed", "error"):
                badge_cls, badge_text = "score-low", "FAILED"
            elif status == "dry_run":
                badge_cls, badge_text = "score-mid", "DRY RUN"
            else:
                badge_cls, badge_text = "score-high", "SUBMITTED"

            platform_tag = f'<span class="source-tag">{platform}</span> ' if platform else ""
            error_html = f'<div class="reason-box" style="border-left-color:#e8c4c4;">{error_msg}</div>' if error_msg else ""

            st.markdown(
                f'<div class="job-card">'
                f'  <div class="job-title">'
                f'    <span class="score-pill {badge_cls}">{badge_text}</span>'
                f'    {job.get("title", "")}'
                f'  </div>'
                f'  <div class="job-company">{job.get("company", "")} &nbsp;·&nbsp; {platform_tag}'
                f'    {(job.get("applied_at") or "")[:16]}'
                f'  </div>'
                f'  {error_html}'
                f'</div>',
                unsafe_allow_html=True,
            )

            if status in ("failed", "error") and job.get("url"):
                col_link, col_resume, _ = st.columns([1.5, 1.5, 7])
                with col_link:
                    st.markdown(f"[Open job posting →]({job['url']})")
                with col_resume:
                    idx = find_job_index_in_filtered(job.get("url", ""))
                    if idx is not None:
                        if st.button("Build Resume", key=f"rebuild_{job.get('source_job_id', '')}"):
                            build_resume_background(idx)
                            st.toast(f"Building resume for {job.get('title')}")
            elif job.get("url"):
                st.markdown(f"[Open job posting →]({job['url']})")


# ── Tab 4 : Generate Resume ──────────────────────────────────────────────────
with tab_custom:
    st.markdown("### Paste a job description and generate a tailored resume")
    st.caption("Step 1: paste the JD and click **Extract Fields** — Step 2: review/edit the extracted info, then click **Generate Resume**.")

    # ── Session-state keys for extracted fields
    for _key, _default in [
        ("custom_title",    ""),
        ("custom_company",  ""),
        ("custom_location", ""),
        ("custom_url",      ""),
        ("custom_desc",     ""),
        ("extracted",       False),
    ]:
        if _key not in st.session_state:
            st.session_state[_key] = _default

    # ── Job description text area (always visible)
    custom_desc = st.text_area(
        "Job Description",
        value=st.session_state.custom_desc,
        placeholder="Paste the full job description here...",
        height=220,
        key="_jd_input",
    )
    st.session_state.custom_desc = custom_desc

    # ── Phase 1: Extract button
    if st.button("Extract Fields", use_container_width=False):
        if not custom_desc.strip():
            st.warning("Please paste a job description first.")
        else:
            with st.spinner("Extracting job details with AI..."):
                fields = extract_job_fields(custom_desc.strip())
            if fields.get("_error"):
                st.error(f"Extraction failed: {fields['_error']}")
            else:
                # Write directly into the widget keys so the inputs show the values
                st.session_state["_ct"] = fields.get("title",    "")
                st.session_state["_cc"] = fields.get("company",  "")
                st.session_state["_cl"] = fields.get("location", "")
                st.session_state["_cu"] = fields.get("url",      "")
                st.session_state.custom_title    = st.session_state["_ct"]
                st.session_state.custom_company  = st.session_state["_cc"]
                st.session_state.custom_location = st.session_state["_cl"]
                st.session_state.custom_url      = st.session_state["_cu"]
                st.session_state.extracted       = True
                st.success("Fields extracted — review and edit below, then click Generate Resume.")

    # ── Phase 2: editable fields + Generate button (always shown, pre-filled after extraction)
    st.markdown("<br>", unsafe_allow_html=True)
    col_left, col_right = st.columns([1, 1])
    with col_left:
        custom_title    = st.text_input("Job Title *",    placeholder="e.g. Software Engineer",  key="_ct")
        custom_company  = st.text_input("Company",        placeholder="e.g. Stripe",             key="_cc")
    with col_right:
        custom_location = st.text_input("Location",       placeholder="e.g. Remote, USA",        key="_cl")
        custom_url      = st.text_input("Job URL",        placeholder="https://...",             key="_cu")

    st.markdown("<br>", unsafe_allow_html=True)

    if st.button("Generate Resume", use_container_width=False):
        _title    = st.session_state.get("_ct", "").strip()
        _company  = st.session_state.get("_cc", "").strip()
        _location = st.session_state.get("_cl", "").strip()
        _url      = st.session_state.get("_cu", "").strip()
        if not st.session_state.custom_desc.strip():
            st.warning("Please paste a job description before generating.")
        elif not _title:
            st.warning("Please enter a job title (or run Extract Fields first).")
        else:
            job_data = [{
                "title":         _title,
                "company":       _company or "Unknown",
                "location":      _location or "USA",
                "url":           _url or "",
                "description":   st.session_state.custom_desc.strip(),
                "source":        "manual",
                "source_job_id": f"manual_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                "posted_at":     datetime.utcnow().strftime("%Y-%m-%d"),
            }]

            tmp_path = os.path.join(BASE_DIR, "output", "_custom_job.json")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(job_data, f, indent=2, ensure_ascii=False)

            with st.spinner(f"Building tailored resume for {_title} @ {_company or 'Unknown'} — this takes 20–40 seconds..."):
                result = subprocess.run(
                    [sys.executable,
                     os.path.join(BASE_DIR, "src", "build_all_resumes.py"),
                     "--jobs-file", tmp_path,
                     "--reset"],
                    cwd=BASE_DIR,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )

            if result.returncode == 0 and "Success : 1" in result.stdout:
                safe_title   = re.sub(r'[^\w\-]', '_', _title)
                safe_company = re.sub(r'[^\w\-]', '_', (_company or "Unknown"))
                pdf_name = f"{safe_company}_{safe_title}.pdf"
                pdf_path = os.path.join(BASE_DIR, "resumes", pdf_name)
                if os.path.exists(pdf_path):
                    st.success(f"Resume generated: resumes/{pdf_name}")
                else:
                    pdfs = sorted(
                        [f for f in os.listdir(os.path.join(BASE_DIR, "resumes")) if f.endswith(".pdf")],
                        key=lambda f: os.path.getmtime(os.path.join(BASE_DIR, "resumes", f)),
                        reverse=True,
                    )
                    st.success(f"Resume generated: resumes/{pdfs[0]}" if pdfs else "Resume generated — check the resumes/ folder.")
            else:
                st.error("Resume generation failed. Check the output below.")
                if result.stdout:
                    with st.expander("Build output"):
                        st.text(result.stdout[-3000:])
                if result.stderr:
                    with st.expander("Errors"):
                        st.text(result.stderr[-2000:])


# ── Tab 5 : Setup ────────────────────────────────────────────────────────────
with tab_setup:
    PROFILE_PATH   = os.path.join(BASE_DIR, "profile.txt")
    BASE_YAML_PATH = os.path.join(BASE_DIR, os.getenv("BASE_YAML_NAME", "base_resume.yaml"))
    ENV_PATH       = os.path.join(BASE_DIR, ".env")

    def read_env() -> dict:
        result = {}
        if os.path.exists(ENV_PATH):
            with open(ENV_PATH, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k, _, v = line.partition("=")
                        result[k.strip()] = v.strip()
        return result

    def write_env(updates: dict):
        existing = read_env()
        existing.update({k: v for k, v in updates.items() if v.strip()})
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            for k, v in existing.items():
                f.write(f"{k}={v}\n")

    st.markdown("### Setup — Configure Your Profile & API Keys")
    st.caption(
        "All settings are saved locally to your machine. "
        "Nothing is pushed to git (profile, YAML, and .env are in .gitignore)."
    )

    # ── Section 1: Candidate Profile ─────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 1 · Candidate Profile")
    st.caption(
        "This text is fed to the AI ranker to score job fit. "
        "Write your skills, experience summary, and scoring preferences. "
        "Structure it with sections: `=== IDENTITY ===`, `=== EXPERIENCE ===`, "
        "`=== TECH STACK ===`, and `=== SCORING CRITERIA ===`."
    )

    current_profile = ""
    if os.path.exists(PROFILE_PATH):
        with open(PROFILE_PATH, encoding="utf-8") as f:
            current_profile = f.read()

    new_profile = st.text_area(
        "profile.txt content",
        value=current_profile,
        height=320,
        placeholder=(
            "PURPOSE: This profile is used by an AI system to score job postings.\n\n"
            "=== IDENTITY ===\nName: Your Name\nDegree: ...\nVisa Status: ...\n\n"
            "=== EXPERIENCE ===\n...\n\n=== TECH STACK ===\n...\n\n"
            "=== SCORING CRITERIA ===\n+2 if: LLM/AI/RAG core to role\n-3 if: Requires 3+ years\n..."
        ),
        label_visibility="collapsed",
    )
    if st.button("Save Profile", key="setup_save_profile"):
        with open(PROFILE_PATH, "w", encoding="utf-8") as f:
            f.write(new_profile)
        st.success("profile.txt saved.")

    # ── Section 2: Base Resume YAML ───────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 2 · Base Resume YAML (RenderCV format)")
    st.caption(
        "Upload your resume as a [RenderCV](https://rendercv.com) YAML file, "
        "or paste the YAML directly. "
        "This is the source-of-truth resume — the AI tailors a copy per job."
    )

    col_upload, col_paste = st.columns([1, 2])

    with col_upload:
        st.markdown("**Upload a .yaml file**")
        uploaded_yaml = st.file_uploader(
            "Upload YAML",
            type=["yaml", "yml"],
            key="setup_yaml_upload",
            label_visibility="collapsed",
        )
        if uploaded_yaml is not None:
            try:
                yaml_from_upload = uploaded_yaml.read().decode("utf-8-sig")
                yaml.safe_load(yaml_from_upload)   # validate
                with open(BASE_YAML_PATH, "w", encoding="utf-8") as f:
                    f.write(yaml_from_upload)
                st.success(f"Saved as {os.path.basename(BASE_YAML_PATH)}")
            except UnicodeDecodeError:
                st.error("Encoding error — save the file as UTF-8 and try again.")
            except yaml.YAMLError as e:
                st.error(f"Invalid YAML: {e}")

    with col_paste:
        st.markdown("**Or paste YAML directly**")
        current_yaml = ""
        if os.path.exists(BASE_YAML_PATH):
            with open(BASE_YAML_PATH, encoding="utf-8-sig") as f:
                current_yaml = f.read()

        yaml_text = st.text_area(
            "YAML content",
            value=current_yaml,
            height=280,
            placeholder="Paste your RenderCV YAML here...",
            label_visibility="collapsed",
            key="setup_yaml_paste",
        )
        if st.button("Save YAML", key="setup_save_yaml"):
            try:
                yaml.safe_load(yaml_text)
                with open(BASE_YAML_PATH, "w", encoding="utf-8") as f:
                    f.write(yaml_text)
                st.success(f"Saved as {os.path.basename(BASE_YAML_PATH)}")
            except yaml.YAMLError as e:
                st.error(f"Invalid YAML — fix the error before saving: {e}")

    # ── Section 3: API Keys ───────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 3 · API Keys & Endpoints")
    st.caption(
        "Keys are written to `.env` and are never committed to git. "
        "Leave a field blank to keep the existing value."
    )

    cfg_setup = load_config()
    azure_cfg_setup = cfg_setup.get("azure_openai", {})

    col_az, col_other = st.columns(2)

    with col_az:
        st.markdown("**Azure OpenAI**")
        setup_az_endpoint = st.text_input(
            "Endpoint URL",
            value=azure_cfg_setup.get("endpoint", ""),
            placeholder="https://YOUR_RESOURCE.openai.azure.com",
            key="setup_az_endpoint",
        )
        setup_az_deployment = st.text_input(
            "Deployment name",
            value=azure_cfg_setup.get("deployment", ""),
            placeholder="gpt-4o",
            key="setup_az_deployment",
        )
        setup_az_key = st.text_input(
            "API Key",
            type="password",
            placeholder="Leave blank to keep existing",
            key="setup_az_key",
        )

    with col_other:
        st.markdown("**Other APIs**")
        setup_apify_key = st.text_input(
            "Apify Token  (LinkedIn job fetching)",
            type="password",
            placeholder="apify_api_...",
            key="setup_apify",
        )
        setup_az_id = st.text_input(
            "Adzuna App ID",
            placeholder="from developer.adzuna.com",
            key="setup_adzuna_id",
        )
        setup_az_appkey = st.text_input(
            "Adzuna App Key",
            type="password",
            placeholder="from developer.adzuna.com",
            key="setup_adzuna_key",
        )
        setup_oai_key = st.text_input(
            "OpenAI API Key  (optional — use instead of Azure)",
            type="password",
            placeholder="sk-...",
            key="setup_oai",
        )

    if st.button("Save API Keys & Endpoints", key="setup_save_keys", type="primary"):
        changed_config = False
        if setup_az_endpoint.strip():
            cfg_setup["azure_openai"]["endpoint"] = setup_az_endpoint.strip()
            changed_config = True
        if setup_az_deployment.strip():
            cfg_setup["azure_openai"]["deployment"] = setup_az_deployment.strip()
            changed_config = True
        if changed_config:
            save_config(cfg_setup)

        write_env({
            "AZURE_OPENAI_API_KEY": setup_az_key,
            "APIFY_TOKEN":          setup_apify_key,
            "ADZUNA_APP_ID":        setup_az_id,
            "ADZUNA_APP_KEY":       setup_az_appkey,
            "OPENAI_API_KEY":       setup_oai_key,
        })
        st.success("Saved. Restart the app (`Ctrl+C` then re-run) to apply new API keys.")

    # ── Section 4: Greenhouse companies ──────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 4 · Greenhouse Company List")
    st.caption(
        "One slug per line — the part after `https://boards.greenhouse.io/`. "
        "e.g. `openai`, `anthropic`, `stripe`."
    )
    current_slugs = "\n".join(cfg_setup.get("greenhouse_companies", []))
    new_slugs = st.text_area(
        "Greenhouse slugs",
        value=current_slugs,
        height=180,
        label_visibility="collapsed",
        key="setup_greenhouse",
    )
    if st.button("Save Greenhouse List", key="setup_save_greenhouse"):
        slugs = [s.strip() for s in new_slugs.splitlines() if s.strip()]
        cfg_setup["greenhouse_companies"] = slugs
        save_config(cfg_setup)
        st.success(f"Saved {len(slugs)} company slug(s).")

    # ── Section 5: Status check ───────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Setup Status")
    env_vals = read_env()
    checks = {
        "profile.txt exists":          os.path.exists(PROFILE_PATH),
        "Base resume YAML exists":      os.path.exists(BASE_YAML_PATH),
        ".env exists":                  os.path.exists(ENV_PATH),
        "AZURE_OPENAI_API_KEY set":     bool(env_vals.get("AZURE_OPENAI_API_KEY") or os.getenv("AZURE_OPENAI_API_KEY")),
        "APIFY_TOKEN set":              bool(env_vals.get("APIFY_TOKEN") or os.getenv("APIFY_TOKEN")),
        "ADZUNA_APP_ID set":            bool(env_vals.get("ADZUNA_APP_ID") or os.getenv("ADZUNA_APP_ID")),
        "Azure endpoint configured":    bool(azure_cfg_setup.get("endpoint")),
        "Azure deployment configured":  bool(azure_cfg_setup.get("deployment")),
    }
    c1, c2 = st.columns(2)
    for i, (label, ok) in enumerate(checks.items()):
        col = c1 if i % 2 == 0 else c2
        icon = "✅" if ok else "⚠️"
        col.markdown(f"{icon} &nbsp; {label}", unsafe_allow_html=True)
