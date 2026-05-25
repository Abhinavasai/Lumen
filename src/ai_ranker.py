"""
ai_ranker.py
Scores the latest batch of jobs against the candidate profile using Azure OpenAI.
Writes ai_score + ai_reason back to SQLite and dumps top-N to top25_jobs.json.
"""
import json
import os
import re
import sqlite3
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


def score_job(client: AzureOpenAI, deployment: str, profile: str, job: dict) -> tuple[int, str]:
    """Ask the model to score job fit 1-10 with a one-line reason."""
    jd_snippet = (
        f"Company: {job.get('company', 'Unknown')}\n"
        f"Title: {job.get('title', '')}\n"
        f"Location: {job.get('location', '')}\n"
        f"Source: {job.get('source', '')}\n"
        f"H1B Friendly: {'Yes' if job.get('h1b_friendly') else 'Unknown'}\n\n"
        f"Description:\n{job.get('description', '')[:3000]}"
    )

    prompt = (
        "You are a job-fit evaluator. Score how well this job matches the candidate profile.\n\n"
        f"CANDIDATE PROFILE:\n{profile}\n\n"
        f"JOB POSTING:\n{jd_snippet}\n\n"
        "Respond with ONLY a JSON object â€” no markdown, no explanation outside the JSON:\n"
        '{"score": <1-10 integer>, "reason": "<one sentence, max 20 words>"}\n\n'
        "Use the scoring criteria at the bottom of the profile."
    )

    try:
        response = client.responses.create(
            model=deployment,
            input=prompt,
        )
        text = response.output_text.strip()
        # Extract JSON even if model wraps it in markdown fences
        match = re.search(r"\{.*?\}", text, re.DOTALL)
        if match:
            result = json.loads(match.group())
            score = max(1, min(10, int(result.get("score", 5))))
            reason = str(result.get("reason", "")).strip()
            return score, reason
    except Exception as e:
        print(f"    [ai_ranker] Scoring error for '{job.get('title')}': {e}")

    return 0, "Could not score"


def rank_jobs() -> list:
    config = load_config()
    top_n = config["ai_ranking"]["top_n"]
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
        score, reason = score_job(client, deployment, profile, job)
        job["ai_score"] = score
        job["ai_reason"] = reason
        scored.append(job)
        print(f"  [{i:02d}/{len(jobs)}] {job['title']} @ {job['company']}  â†’  {score}/10  |  {reason}")

    scored.sort(key=lambda x: x["ai_score"], reverse=True)
    top = scored[:top_n]

    # Persist scores back to SQLite
    conn = sqlite3.connect(DB_PATH)
    for job in scored:
        conn.execute(
            "UPDATE jobs SET ai_score = ?, ai_reason = ? WHERE id = ?",
            (job["ai_score"], job["ai_reason"], job["id"]),
        )
    conn.commit()
    conn.close()

    with open(RANKED_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(top, f, indent=2, ensure_ascii=False)

    print(f"\n[ai_ranker] Top {len(top)} jobs saved to {RANKED_OUTPUT}")
    return top


if __name__ == "__main__":
    rank_jobs()

