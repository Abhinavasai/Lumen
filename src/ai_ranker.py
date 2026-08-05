"""
ai_ranker.py
Scores the latest batch of jobs against the candidate profile using Azure OpenAI.
Writes ai_score + ai_reason back to SQLite and dumps top-N to top25_jobs.json.
"""
import json
import os
import re
import sqlite3
import time
import yaml
from openai import AzureOpenAI
from dotenv import load_dotenv

# ── Path resolution ─────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
DB_DIR = os.path.join(BASE_DIR, "db")
load_dotenv(os.path.join(BASE_DIR, ".env"))

DB_PATH = os.path.join(DB_DIR, "jobs.db")
RANKED_OUTPUT = os.path.join(OUTPUT_DIR, "top25_jobs.json")
PROFILE_PATH = os.path.join(BASE_DIR, "profile.txt")


def load_config():
    with open(os.path.join(BASE_DIR, "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_profile() -> str:
    with open(PROFILE_PATH, encoding="utf-8") as f:
        return f.read()


def get_client(config):
    azure_cfg = config["azure_openai"]
    client = AzureOpenAI(
        azure_endpoint=azure_cfg["endpoint"],
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version="2025-03-01-preview",  # required for responses API
    )
    return client, azure_cfg["deployment"]


def score_job(client: AzureOpenAI, deployment: str, profile: str, job: dict,
              min_score: int = 5) -> tuple[int, str]:
    """Ask the model to score job fit 1-10 with a one-line reason."""
    jd_snippet = (
        f"Company: {job.get('company', 'Unknown')}\n"
        f"Title: {job.get('title', '')}\n"
        f"Location: {job.get('location', '')}\n"
        f"Source: {job.get('source', '')}\n"
        f"H1B Friendly: {'Yes' if job.get('h1b_friendly') else 'Unknown'}\n\n"
        f"Description:\n{job.get('description', '')}"
    )

    prompt = (
        "You are a job-fit evaluator. Score how well this job matches the candidate profile.\n\n"
        f"CANDIDATE PROFILE:\n{profile}\n\n"
        f"JOB POSTING:\n{jd_snippet}\n\n"
        "Respond with ONLY a JSON object -- no markdown, no explanation outside the JSON:\n"
        '{"score": <1-10 integer>, "reason": "<one sentence, max 20 words>"}\n\n'
        "Use the scoring criteria at the bottom of the profile."
    )

    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            response = client.responses.create(
                model=deployment,
                input=prompt,
            )
            text = response.output_text.strip()
            match = re.search(r"\{.*?\}", text, re.DOTALL)
            if match:
                result = json.loads(match.group())
                score = max(1, min(10, int(result.get("score", 5))))
                reason = str(result.get("reason", "")).strip()
                return score, reason
        except Exception as e:
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            print(f"    [ai_ranker] Scoring error for '{job.get('title')}' after {max_retries + 1} attempts: {e}")

    return min_score, "Scoring failed - default pass"


def rank_jobs() -> list:
    config = load_config()
    top_n = config["ai_ranking"]["top_n"]
    min_score = config["ai_ranking"].get("min_score", 5)
    profile = load_profile()
    client, deployment = get_client(config)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Load already-applied job IDs to skip them
    try:
        applied_ids = {
            row[0] for row in conn.execute("SELECT source_job_id FROM applied_jobs").fetchall()
        }
    except Exception:
        applied_ids = set()

    # Fetch only the current run's jobs (status = 'new'), excluding already applied
    jobs = conn.execute("""
        SELECT * FROM jobs
        WHERE run_date = (SELECT MAX(run_date) FROM jobs)
        ORDER BY id
    """).fetchall()
    conn.close()

    jobs = [dict(j) for j in jobs if j["source_job_id"] not in applied_ids]

    if applied_ids:
        print(f"[ai_ranker] Skipping {len(applied_ids)} already-applied jobs.")

    if not jobs:
        print("[ai_ranker] No jobs to rank.")
        return []

    print(f"[ai_ranker] Scoring {len(jobs)} jobs with Azure OpenAI ({deployment})...")

    scored = []
    for i, job in enumerate(jobs, 1):
        score, reason = score_job(client, deployment, profile, job, min_score=min_score)
        job["ai_score"] = score
        job["ai_reason"] = reason
        scored.append(job)
        print(f"  [{i:02d}/{len(jobs)}] {job['title']} @ {job['company']}  â†'  {score}/10  |  {reason}")

    scored.sort(key=lambda x: x["ai_score"], reverse=True)
    qualified = [j for j in scored if j["ai_score"] >= min_score]
    top = qualified[:top_n]

    dropped = len(scored) - len(qualified)
    if dropped:
        print(f"[ai_ranker] Dropped {dropped} job(s) scoring below {min_score}/10.")

    # Persist scores back to SQLite
    conn = sqlite3.connect(DB_PATH)

    # Ensure new columns exist (migrate older databases)
    existing = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    for col, default in [("is_top_pick", "0"), ("dismissed", "0")]:
        if col not in existing:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} INTEGER DEFAULT {default}")

    # Reset is_top_pick for this run before re-stamping
    conn.execute("UPDATE jobs SET is_top_pick = 0 WHERE run_date = (SELECT MAX(run_date) FROM jobs)")

    for job in scored:
        conn.execute(
            "UPDATE jobs SET ai_score = ?, ai_reason = ? WHERE id = ?",
            (job["ai_score"], job["ai_reason"], job["id"]),
        )

    # Mark top-N as top picks
    top_ids = [job["id"] for job in top]
    for job_id in top_ids:
        conn.execute("UPDATE jobs SET is_top_pick = 1 WHERE id = ?", (job_id,))

    conn.commit()
    conn.close()

    with open(RANKED_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(top, f, indent=2, ensure_ascii=False)

    print(f"\n[ai_ranker] Top {len(top)} jobs saved to {RANKED_OUTPUT}")
    return top


if __name__ == "__main__":
    rank_jobs()

