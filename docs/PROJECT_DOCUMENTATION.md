# Job Hunter Pipeline — Project Documentation

## Overview
This project is a fully automated daily job-hunting pipeline for AI/ML/software roles. It fetches jobs from LinkedIn (via Apify and guest API fallback), Adzuna, and Greenhouse, filters and deduplicates them, stores them in SQLite, ranks them using Azure OpenAI, and presents the results in a Streamlit UI. It is designed for high-volume, sponsorship-friendly job search and can be run manually or scheduled daily.

---

## Directory Structure

```
CronJobs/
├── src/                      # Pipeline scripts
│   ├── fetch_jobs.py         # Step 1: Fetch jobs from all sources → output/raw_jobs.json
│   ├── filter_jobs.py        # Step 2: Filter by title, seniority, location, sponsorship
│   ├── dedupe_jobs.py        # Step 3: Deduplicate jobs → output/deduped_jobs.json
│   ├── save_to_sqlite.py     # Step 4: Save jobs to db/jobs.db
│   ├── ai_ranker.py          # Step 5: Azure OpenAI scoring → output/top25_jobs.json
│   └── run_pipeline.py       # Orchestrator (runs all 5 steps)
├── output/                   # Intermediate JSON files
│   ├── raw_jobs.json
│   ├── filtered_jobs.json
│   ├── deduped_jobs.json
│   └── top25_jobs.json
├── db/                       # SQLite database
│   └── jobs.db
├── docs/                     # Reference documents
│   ├── Abhinava_Sai_Profile.docx
│   └── Prompt.docx
├── app.py                    # Streamlit UI
├── config.yaml               # Keywords, filters, AI settings
├── profile.txt               # Candidate profile for AI scoring
├── .env                      # API keys (never commit)
├── .gitignore
├── requirements.txt
├── README.md
└── setup_scheduler.ps1       # Windows Task Scheduler registration
```

---

## Pipeline Steps

### 1. Fetch Jobs (`src/fetch_jobs.py`)
- **Sources:**
  - LinkedIn (primary: Apify actor, fallback: guest API)
  - Adzuna (US)
  - Greenhouse (top AI/tech companies)
- **Details:**
  - Uses 8+ keywords, fetches up to 25 jobs per keyword
  - Dedupes by job ID
  - Fetches full descriptions for LinkedIn jobs
  - Output: `output/raw_jobs.json`

### 2. Filter Jobs (`src/filter_jobs.py`)
- **Filters:**
  - Title keywords (e.g., "engineer", "AI", "ML")
  - Seniority (excludes "senior", "lead", etc.)
  - Location (US only, with state regex)
  - Sponsorship (hard filter: 28+ phrases)
  - Posted within X hours (configurable)
- **Output:** `output/filtered_jobs.json`

### 3. Deduplicate Jobs (`src/dedupe_jobs.py`)
- Removes duplicate jobs by source_job_id and URL
- Output: `output/deduped_jobs.json`

### 4. Save to SQLite (`src/save_to_sqlite.py`)
- **Database:** `db/jobs.db`
- **Tables:**
  - `jobs` (all jobs)
  - `job_runs` (run metadata)
  - `applied_jobs` (user-applied tracking)
- Upserts jobs and logs each run

### 5. AI Ranking (`src/ai_ranker.py`)
- Uses Azure OpenAI (responses API, `gpt-5.2-codex`)
- Loads candidate profile from `profile.txt`
- Skips jobs already applied to
- Writes top 25 jobs to `output/top25_jobs.json`

---

## Streamlit UI (`app.py`)
- **Tabs:**
  - Top 25 AI Picks
  - All Fetched Jobs
  - Applied Jobs
- **Sidebar:**
  - Keywords, max results, location, posted within hours, top N slider
  - Save config, last run, applied count
  - Run Pipeline Now, Refresh
- **Features:**
  - "Open all" button (opens all job links)
  - Mark jobs as applied
  - Applied jobs tab with history

---

## Configuration
- **config.yaml:**
  - Keywords, filters, AI ranking settings, Greenhouse companies
- **profile.txt:**
  - Graduation, visa status, work authorization, scoring rules
- **.env:**
  - API keys for Azure OpenAI, Apify, Adzuna

---

## Azure OpenAI Details
- **Endpoint:** https://ch-openai-codex-agent-resource.openai.azure.com
- **Deployment:** gpt-5.2-codex
- **API Version:** 2025-01-01-preview
- **API Key:** In `.env` as `AZURE_OPENAI_API_KEY`
- **Usage:**
  - `client.responses.create(model=..., input=...)`
  - Reads `resp.output_text`

---

## Automation
- **Manual run:**
  - `python src/run_pipeline.py`
- **Streamlit UI:**
  - `python -m streamlit run app.py`
- **Scheduled run:**
  - `setup_scheduler.ps1` registers a daily 8 AM Windows Task Scheduler job

---

## Notes
- All paths are project-root relative (auto-detects working directory)
- Output and DB directories are auto-created if missing
- All API keys and sensitive info are kept in `.env` (never commit)
- README and this doc reflect the latest structure and usage

---

## Authors & Contact
- Abhinava Sai Atirunaga
- For questions, see `profile.txt` or contact the project owner.
