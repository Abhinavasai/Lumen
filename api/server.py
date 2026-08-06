"""
FastAPI backend for the Lumen job-hunting dashboard.
The Next.js frontend proxies /api/* to this server at port 8000.

Run:  python api/server.py
"""

import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn
import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── Paths ────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "db" / "jobs.db"
CONFIG_PATH = BASE_DIR / "config.yaml"
PROFILE_PATH = BASE_DIR / "profile.txt"
YAML_PATH = BASE_DIR / os.getenv("BASE_YAML_NAME", "Abhinava_Sai_Tirunagari_CV.yaml")
ENV_PATH = BASE_DIR / ".env"
OUTPUT_DIR = BASE_DIR / "output"

load_dotenv(ENV_PATH)

# ── FastAPI app ──────────────────────────────────────────────
app = FastAPI(title="Lumen Job Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic models ─────────────────────────────────────────
class ApplyBody(BaseModel):
    title: str
    company: str
    url: str
    source_job_id: str


class DismissBody(BaseModel):
    title: str
    company: str
    url: str
    source_job_id: str


class GenerateResumeBody(BaseModel):
    title: str
    company: str
    location: str
    url: str
    description: str


class ExtractBody(BaseModel):
    description: str


class ProfileBody(BaseModel):
    content: str


class YamlBody(BaseModel):
    content: str


class KeysBody(BaseModel):
    AZURE_OPENAI_API_KEY: Optional[str] = None
    APIFY_TOKEN: Optional[str] = None
    ADZUNA_APP_ID: Optional[str] = None
    ADZUNA_APP_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None


# ── DB helpers ───────────────────────────────────────────────
def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def ensure_applied_jobs_table(conn: sqlite3.Connection):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS applied_jobs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            source_job_id   TEXT UNIQUE,
            title           TEXT,
            company         TEXT,
            url             TEXT,
            applied_at      TEXT
        )
        """
    )
    conn.commit()


# ── Config helpers ───────────────────────────────────────────
def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def save_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, allow_unicode=True, sort_keys=False, default_flow_style=False)


def deep_merge(base: dict, overrides: dict) -> dict:
    """Recursively merge overrides into base."""
    merged = dict(base)
    for key, value in overrides.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


# ═════════════════════════════════════════════════════════════
#  ENDPOINTS
# ═════════════════════════════════════════════════════════════


# ── GET /api/jobs ────────────────────────────────────────────
@app.get("/api/jobs")
def get_jobs(top_n: Optional[int] = None):
    conn = get_db()
    try:
        # Find the latest run_date
        row = conn.execute("SELECT MAX(run_date) AS latest FROM jobs").fetchone()
        latest = row["latest"] if row else None
        if not latest:
            return []

        if top_n:
            rows = conn.execute(
                """
                SELECT * FROM jobs
                WHERE run_date = ? AND ai_score IS NOT NULL
                ORDER BY ai_score DESC
                LIMIT ?
                """,
                (latest, top_n),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM jobs
                WHERE run_date = ?
                ORDER BY ai_score DESC
                """,
                (latest,),
            ).fetchall()

        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── GET /api/stats ───────────────────────────────────────────
@app.get("/api/stats")
def get_stats(top_n: Optional[int] = None):
    conn = get_db()
    ensure_applied_jobs_table(conn)
    try:
        row = conn.execute("SELECT MAX(run_date) AS latest FROM jobs").fetchone()
        latest = row["latest"] if row else None

        if not latest:
            return {
                "total_jobs": 0,
                "avg_score": 0,
                "top_score": 0,
                "applied_count": 0,
                "last_run": None,
                "sources": {},
            }

        total_row = conn.execute(
            "SELECT COUNT(*) AS total_jobs FROM jobs WHERE run_date = ?",
            (latest,),
        ).fetchone()

        if top_n:
            score_rows = conn.execute(
                """
                SELECT ai_score FROM jobs
                WHERE run_date = ? AND ai_score IS NOT NULL
                ORDER BY ai_score DESC
                LIMIT ?
                """,
                (latest, top_n),
            ).fetchall()
            scores = [r["ai_score"] for r in score_rows]
            avg_score = round(sum(scores) / len(scores), 2) if scores else 0
            top_score = scores[0] if scores else 0
        else:
            stats_row = conn.execute(
                """
                SELECT
                    COALESCE(AVG(ai_score), 0) AS avg_score,
                    COALESCE(MAX(ai_score), 0) AS top_score
                FROM jobs
                WHERE run_date = ? AND ai_score IS NOT NULL
                """,
                (latest,),
            ).fetchone()
            avg_score = round(stats_row["avg_score"], 2)
            top_score = stats_row["top_score"]

        applied_row = conn.execute("SELECT COUNT(*) AS cnt FROM applied_jobs").fetchone()

        source_rows = conn.execute(
            """
            SELECT source, COUNT(*) AS cnt
            FROM jobs
            WHERE run_date = ?
            GROUP BY source
            """,
            (latest,),
        ).fetchall()

        sources = {r["source"]: r["cnt"] for r in source_rows}

        return {
            "total_jobs": total_row["total_jobs"],
            "avg_score": avg_score,
            "top_score": top_score,
            "applied_count": applied_row["cnt"],
            "last_run": latest,
            "sources": sources,
        }
    finally:
        conn.close()


# ── GET /api/applied ─────────────────────────────────────────
@app.get("/api/applied")
def get_applied():
    conn = get_db()
    ensure_applied_jobs_table(conn)
    try:
        rows = conn.execute(
            "SELECT * FROM applied_jobs ORDER BY applied_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── POST /api/apply ──────────────────────────────────────────
@app.post("/api/apply")
def apply_job(body: ApplyBody):
    conn = get_db()
    ensure_applied_jobs_table(conn)
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO applied_jobs (source_job_id, title, company, url, applied_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (body.source_job_id, body.title, body.company, body.url, datetime.now().isoformat()),
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


# ── POST /api/apply-all ─────────────────────────────────────
@app.post("/api/apply-all")
def apply_all(jobs: List[ApplyBody]):
    conn = get_db()
    ensure_applied_jobs_table(conn)
    try:
        count = 0
        for job in jobs:
            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO applied_jobs (source_job_id, title, company, url, applied_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (job.source_job_id, job.title, job.company, job.url, datetime.now().isoformat()),
                )
                count += 1
            except Exception:
                pass
        conn.commit()
        return {"ok": True, "count": count}
    finally:
        conn.close()


# ── POST /api/dismiss ────────────────────────────────────────
@app.post("/api/dismiss")
def dismiss_job(body: DismissBody):
    conn = get_db()
    ensure_applied_jobs_table(conn)
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO applied_jobs (source_job_id, title, company, url, applied_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (body.source_job_id, body.title, body.company, body.url, datetime.now().isoformat()),
        )
        conn.execute("DELETE FROM jobs WHERE url = ?", (body.url,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


# ── POST /api/auto-apply ────────────────────────────────────
@app.post("/api/auto-apply")
def auto_apply_jobs(dry_run: bool = False, source: Optional[str] = None):
    """Trigger auto-apply for Greenhouse/Ashby/Lever/Workday/SmartRecruiters/Workable/BambooHR jobs."""
    kwargs: Dict[str, Any] = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE

    cmd = [sys.executable, str(BASE_DIR / "src" / "auto_apply.py")]
    if dry_run:
        cmd.append("--dry-run")
    if source:
        cmd.extend(["--source", source])

    subprocess.Popen(cmd, cwd=str(BASE_DIR), **kwargs)
    mode = "dry-run" if dry_run else "live"
    return {"message": f"Auto-apply started ({mode})", "dry_run": dry_run, "source": source}


# ── GET /api/auto-apply/status ──────────────────────────────
@app.get("/api/auto-apply/status")
def auto_apply_status():
    """Return counts from applied_jobs grouped by status and platform."""
    conn = get_db()
    ensure_applied_jobs_table(conn)
    try:
        existing = {r[1] for r in conn.execute("PRAGMA table_info(applied_jobs)").fetchall()}
        if "platform" not in existing or "status" not in existing:
            total = conn.execute("SELECT COUNT(*) AS cnt FROM applied_jobs").fetchone()
            return {"total": total["cnt"], "by_status": {"submitted": total["cnt"]}, "by_platform": {}}

        status_rows = conn.execute(
            "SELECT status, COUNT(*) AS cnt FROM applied_jobs GROUP BY status"
        ).fetchall()
        platform_rows = conn.execute(
            "SELECT platform, COUNT(*) AS cnt FROM applied_jobs WHERE platform != '' GROUP BY platform"
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) AS cnt FROM applied_jobs").fetchone()

        return {
            "total": total["cnt"],
            "by_status": {r["status"]: r["cnt"] for r in status_rows},
            "by_platform": {r["platform"]: r["cnt"] for r in platform_rows},
        }
    finally:
        conn.close()


# ── GET /api/auto-apply/results ────────────────────────────
@app.get("/api/auto-apply/results")
def auto_apply_results(status: Optional[str] = None):
    """Return all applied_jobs with full details, optionally filtered by status."""
    conn = get_db()
    ensure_applied_jobs_table(conn)
    try:
        existing = {r[1] for r in conn.execute("PRAGMA table_info(applied_jobs)").fetchall()}
        has_extra = "platform" in existing and "status" in existing and "error" in existing

        if has_extra:
            if status:
                rows = conn.execute(
                    "SELECT source_job_id, title, company, url, applied_at, platform, status, error "
                    "FROM applied_jobs WHERE status = ? ORDER BY applied_at DESC",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT source_job_id, title, company, url, applied_at, platform, status, error "
                    "FROM applied_jobs ORDER BY applied_at DESC"
                ).fetchall()
        else:
            rows = conn.execute(
                "SELECT source_job_id, title, company, url, applied_at FROM applied_jobs ORDER BY applied_at DESC"
            ).fetchall()

        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── GET /api/resumes/list ───────────────────────────────────
@app.get("/api/resumes/list")
def list_resumes():
    """List all PDF resumes in the resumes/ directory."""
    resumes_dir = BASE_DIR / "resumes"
    if not resumes_dir.exists():
        return []
    return sorted(
        [f.name for f in resumes_dir.iterdir() if f.suffix.lower() == ".pdf"],
        key=str.lower,
    )


# ── POST /api/auto-apply/single ───────────────────────────
class SingleApplyBody(BaseModel):
    url: str
    resume_name: str
    cover_letter_path: Optional[str] = None
    dry_run: bool = False


@app.post("/api/auto-apply/single")
def auto_apply_single(body: SingleApplyBody):
    """Apply to a single job by URL with a chosen resume."""
    import importlib.util

    resume_path = BASE_DIR / "resumes" / body.resume_name
    if not resume_path.exists():
        raise HTTPException(status_code=400, detail=f"Resume not found: {body.resume_name}")

    import sys
    src_dir = str(BASE_DIR / "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    spec = importlib.util.spec_from_file_location("auto_apply", BASE_DIR / "src" / "auto_apply.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    result = mod.single_apply(
        url=body.url,
        resume_path=str(resume_path),
        cover_letter_path=body.cover_letter_path or "",
        dry_run=body.dry_run,
    )
    return result


# ── GET /api/auto-apply/progress ────────────────────────────
@app.get("/api/auto-apply/progress")
def auto_apply_progress():
    """Return live progress from the currently running (or last) auto-apply."""
    progress_file = OUTPUT_DIR / "auto_apply_progress.json"
    if not progress_file.exists():
        return {"running": False, "total": 0, "current": 0, "results": []}
    try:
        with open(progress_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"running": False, "total": 0, "current": 0, "results": []}


# ── POST /api/pipeline/run ───────────────────────────────────
@app.post("/api/pipeline/run")
def run_pipeline():
    conn = get_db()
    try:
        conn.execute("DELETE FROM jobs")
        conn.commit()
    finally:
        conn.close()

    kwargs: Dict[str, Any] = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE

    subprocess.Popen(
        [sys.executable, str(BASE_DIR / "src" / "run_pipeline.py")],
        cwd=str(BASE_DIR),
        **kwargs,
    )
    return {"message": "Pipeline started"}


# ── POST /api/resumes/build-all ──────────────────────────────
@app.post("/api/resumes/build-all")
def build_all_resumes():
    kwargs: Dict[str, Any] = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE

    subprocess.Popen(
        [sys.executable, str(BASE_DIR / "src" / "build_all_resumes.py"), "--reset"],
        cwd=str(BASE_DIR),
        **kwargs,
    )
    return {"message": "Resume builder started"}


# ── POST /api/resumes/generate ───────────────────────────────
@app.post("/api/resumes/generate")
def generate_resume(body: GenerateResumeBody):
    os.makedirs(str(OUTPUT_DIR), exist_ok=True)
    custom_job_path = OUTPUT_DIR / "_custom_job.json"

    job_data = [
        {
            "title": body.title,
            "company": body.company,
            "location": body.location,
            "url": body.url,
            "description": body.description,
        }
    ]
    with open(custom_job_path, "w", encoding="utf-8") as f:
        json.dump(job_data, f, ensure_ascii=False, indent=2)

    env = {
        **os.environ,
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
    }

    try:
        result = subprocess.run(
            [
                sys.executable,
                str(BASE_DIR / "src" / "build_all_resumes.py"),
                "--jobs-file",
                str(custom_job_path),
                "--reset",
            ],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=300,
        )

        stdout = result.stdout or ""
        stderr = result.stderr or ""

        if result.returncode == 0:
            # Try to find the generated PDF path from stdout
            pdf_path = None
            for line in stdout.splitlines():
                if "Saved:" in line:
                    match = re.search(r"Saved:\s*(.+\.pdf)", line)
                    if match:
                        pdf_path = match.group(1).strip()
                        break

            return {
                "success": True,
                "pdf_path": pdf_path,
                "stdout": stdout,
            }
        else:
            return {
                "success": False,
                "error": stderr or stdout,
                "stdout": stdout,
            }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Resume generation timed out after 300 seconds",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


# ── POST /api/extract ───────────────────────────────────────
@app.post("/api/extract")
def extract_job_info(body: ExtractBody):
    import openai

    cfg = load_config()
    azure_cfg = cfg.get("azure_openai", {})
    endpoint = azure_cfg.get("endpoint")
    deployment = azure_cfg.get("deployment")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")

    if not endpoint or not deployment or not api_key:
        raise HTTPException(
            status_code=500,
            detail="Azure OpenAI not configured. Set endpoint/deployment in config.yaml and AZURE_OPENAI_API_KEY in .env.",
        )

    client = openai.AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version="2025-03-01-preview",
    )

    prompt = f"""Extract the following fields from this job posting description. Return ONLY valid JSON with these keys: title, company, location, url

If a field cannot be determined, use an empty string.

Job posting:
{body.description}
"""

    try:
        response = client.responses.create(
            model=deployment,
            input=[
                {
                    "role": "system",
                    "content": "You are a job posting parser. Return only valid JSON, no markdown, no explanation.",
                },
                {"role": "user", "content": prompt},
            ],
        )

        raw = (response.output_text or "").strip()
        # Strip markdown code fences if present
        raw = re.sub(r"^```json?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)

        extracted = json.loads(raw)
        return {
            "title": extracted.get("title", ""),
            "company": extracted.get("company", ""),
            "location": extracted.get("location", ""),
            "url": extracted.get("url", ""),
        }

    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail=f"Failed to parse AI response as JSON: {raw}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── GET /api/config ──────────────────────────────────────────
@app.get("/api/config")
def get_config():
    return load_config()


# ── PUT /api/config ──────────────────────────────────────────
@app.put("/api/config")
def update_config(body: dict):
    cfg = load_config()
    merged = deep_merge(cfg, body)
    save_config(merged)
    return {"ok": True}


# ── GET /api/profile ─────────────────────────────────────────
@app.get("/api/profile")
def get_profile():
    if not PROFILE_PATH.exists():
        return {"content": ""}
    with open(PROFILE_PATH, "r", encoding="utf-8") as f:
        return {"content": f.read()}


# ── PUT /api/profile ─────────────────────────────────────────
@app.put("/api/profile")
def update_profile(body: ProfileBody):
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        f.write(body.content)
    return {"ok": True}


# ── GET /api/yaml ────────────────────────────────────────────
@app.get("/api/yaml")
def get_yaml():
    if not YAML_PATH.exists():
        return {"content": ""}
    with open(YAML_PATH, "r", encoding="utf-8") as f:
        return {"content": f.read()}


# ── PUT /api/yaml ────────────────────────────────────────────
@app.put("/api/yaml")
def update_yaml(body: YamlBody):
    try:
        yaml.safe_load(body.content)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {e}")

    with open(YAML_PATH, "w", encoding="utf-8") as f:
        f.write(body.content)
    return {"ok": True}


# ── PUT /api/keys ────────────────────────────────────────────
@app.put("/api/keys")
def update_keys(body: KeysBody):
    # Read existing .env lines
    existing: Dict[str, str] = {}
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    existing[key.strip()] = value.strip()

    # Merge non-empty values from the request body
    updates = body.model_dump(exclude_none=True)
    for key, value in updates.items():
        if value:  # only merge non-empty strings
            existing[key] = value

    # Write back
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        for key, value in existing.items():
            f.write(f"{key}={value}\n")

    return {"ok": True}


# ── GET /api/setup/status ────────────────────────────────────
@app.get("/api/setup/status")
def setup_status():
    cfg = load_config()
    azure_cfg = cfg.get("azure_openai", {})

    return {
        "profile_exists": PROFILE_PATH.exists(),
        "yaml_exists": YAML_PATH.exists(),
        "env_exists": ENV_PATH.exists(),
        "azure_key_set": bool(os.getenv("AZURE_OPENAI_API_KEY")),
        "apify_token_set": bool(os.getenv("APIFY_TOKEN")),
        "adzuna_id_set": bool(os.getenv("ADZUNA_APP_ID")),
        "azure_endpoint_configured": bool(azure_cfg.get("endpoint")),
        "azure_deployment_configured": bool(azure_cfg.get("deployment")),
    }


# ── Main ─────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
