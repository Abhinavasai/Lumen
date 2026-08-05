# Lumen

> *Cut through the noise. Find the signal.*

The job market is loud. Hundreds of postings a day — most irrelevant, many predatory, some genuinely worth your time. **Lumen** is a personal job-hunting pipeline that runs every morning, finds the roles worth applying to, scores them against your profile with AI, and generates a tailored one-page resume for each one — before you've had your first coffee.

It scrapes LinkedIn, Adzuna, and Greenhouse. It filters out senior roles, intern traps, and no-sponsorship dead ends. It ranks what's left using Azure OpenAI and your own scoring criteria. Then it opens a clean UI so you can review, apply, and track — all in one place.

Built for new grads and visa-sponsored candidates navigating the early-career market.

---

## What it does

Automated daily job scraper that fetches entry-level / new-grad CS jobs from LinkedIn (via Apify), Adzuna, and Greenhouse, deduplicates them, and uses Azure OpenAI to rank the top matches against your personal profile — then builds a tailored one-page PDF resume for each job.

---

## Features

- **Multi-source fetching** — LinkedIn via Apify actor + direct guest API (both run simultaneously, merged by URL), Adzuna REST API, Greenhouse board API
- **Smart filtering** — title keywords, seniority/intern exclusion, H1B no-sponsorship signals, US/remote location, recency window
- **H1B awareness** — tags known H1B sponsors; filters out explicit no-sponsorship postings; AI ranker scores confirmed sponsors higher
- **Deduplication** — URL-exact + normalized `company|title|location` key
- **AI ranking** — Azure OpenAI scores each job 1–10 against your profile; returns top N with one-line reasons
- **Tailored resume builder** — GPT rewrites your base RenderCV YAML per job; renders a single-page PDF; auto-trims if 2 pages
- **Synthetic project injection** — adds a JD-targeted portfolio project using only your existing tech stack
- **SQLite storage** — every run is persisted; supports repeated runs without duplicate insertion
- **Next.js dashboard** — Dark-themed glassmorphism UI with FastAPI backend; Dashboard, All Jobs, Applied, Generate Resume, Settings pages
- **Streamlit UI (legacy)** — Setup tab for first-time config; sidebar pipeline controls; Top Picks, All Jobs, Applied, Generate Resume tabs
- **Daily cron** — Windows Task Scheduler runs the pipeline at 8 AM automatically; manual run anytime

---

## Project Structure

```
CronJobs/
├── src/                      ← Pipeline scripts
│   ├── fetch_jobs.py         ← Step 1: fetch from all sources → output/raw_jobs.json
│   ├── filter_jobs.py        ← Step 2: filter by title, seniority, location, date
│   ├── dedupe_jobs.py        ← Step 3: deduplicate → output/deduped_jobs.json
│   ├── save_to_sqlite.py     ← Step 4: UPSERT into db/jobs.db
│   ├── ai_ranker.py          ← Step 5: Azure OpenAI scores → output/top25_jobs.json
│   ├── run_pipeline.py       ← Orchestrator (runs all 5 steps)
│   └── build_all_resumes.py  ← Tailors and renders a PDF resume for each filtered job
├── api/                      ← FastAPI backend (serves Next.js frontend)
│   ├── __init__.py
│   └── server.py             ← 16 REST endpoints wrapping SQLite, config, pipeline
├── frontend/                 ← Next.js 15 dashboard (App Router + Tailwind)
│   ├── app/                  ← Pages: Dashboard, Jobs, Applied, Generate, Settings
│   ├── components/           ← UI primitives + domain components (glassmorphism cards)
│   ├── lib/                  ← API client, utilities
│   ├── types/                ← TypeScript interfaces
│   └── package.json
├── output/                   ← Intermediate JSON files (auto-created)
│   ├── raw_jobs.json
│   ├── filtered_jobs.json
│   ├── deduped_jobs.json
│   └── top25_jobs.json
├── db/                       ← SQLite database (auto-created)
│   └── jobs.db
├── docs/                     ← Reference documents and tailoring prompt
│   ├── ATS_Resume_Tailoring_Prompt.txt  ← GPT prompt for resume tailoring
│   └── PROJECT_DOCUMENTATION.md
├── resumes/                  ← AI-tailored PDF resumes (one per job, auto-created)
├── YOUR_NAME_CV.yaml         ← Base RenderCV resume (source of truth; gitignored)
├── app.py                    ← Streamlit UI (legacy)
├── start_app.bat             ← One-click launcher for Next.js + FastAPI
├── config.yaml               ← Keywords, filters, AI settings
├── profile.txt               ← Candidate profile for AI scoring
├── .env                      ← API keys (never commit)
├── .gitignore
├── requirements.txt
├── README.md
└── setup_scheduler.ps1       ← One-time Windows Task Scheduler registration
```

---

## Prerequisites

- Python 3.9 or higher (tested on 3.12)
- Node.js 18+ and npm (for the Next.js dashboard)
- An **Azure OpenAI** deployment (GPT-4o or later) — OR an OpenAI API key
- An **Apify** account and token — [apify.com](https://apify.com) (used for LinkedIn job scraping; free tier available)
- **Adzuna** API credentials (free tier available at [developer.adzuna.com](https://developer.adzuna.com))
- `rendercv` for PDF resume generation (`pip install "rendercv[full]"`)
- `fastapi` and `uvicorn` for the backend (`pip install fastapi uvicorn`)

---

## Quick Start (New User)

> The **Setup tab** in the Streamlit UI handles everything below interactively. Run the app first (`python -m streamlit run app.py`), open the **Setup** tab, and fill in each section. Or follow the manual steps below.

### 1. Clone and install

```powershell
git clone https://github.com/YOUR_USERNAME/job-hunter.git
cd job-hunter
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install "rendercv[full]"
pip install fastapi uvicorn

# Install frontend dependencies
cd frontend
npm install
cd ..
```

### 2. Create your config file

```powershell
copy config.example.yaml config.yaml
```

Edit `config.yaml` and fill in your Azure OpenAI endpoint and deployment name:

```yaml
azure_openai:
  endpoint: https://YOUR_RESOURCE.openai.azure.com
  deployment: gpt-4o
```

### 3. Set your API keys

You need credentials for three services. Here's how to get each one:

**Apify** (LinkedIn scraper)
1. Sign up at [apify.com](https://apify.com) — free tier gives ~$5/month of compute
2. Go to **Settings → Integrations → API tokens** → click **Create token**
3. Copy the token (starts with `apify_api_...`)

**Adzuna** (job board API)
1. Sign up at [developer.adzuna.com](https://developer.adzuna.com/signup)
2. After login, go to **Dashboard** — your **App ID** and **App Key** are listed there
3. Free tier allows up to 1,000 requests/day

**Azure OpenAI**
1. Create a resource in the [Azure portal](https://portal.azure.com) under **Azure OpenAI**
2. Deploy a model (GPT-4o or later) in **Azure AI Foundry**
3. Go to **Resource → Keys and Endpoint** to copy your key and endpoint URL

Create a `.env` file in the project root (or use the **Setup tab** to enter them in the UI):

```env
AZURE_OPENAI_API_KEY=your_azure_openai_key
APIFY_TOKEN=apify_api_your_token_here
ADZUNA_APP_ID=your_adzuna_app_id
ADZUNA_APP_KEY=your_adzuna_app_key
# Optional: use OpenAI directly instead of Azure
# OPENAI_API_KEY=sk-...
```

### 4. Add your candidate profile

Create `profile.txt` in the project root (or paste it in the **Setup tab → Section 1**).
Structure it like this:

```
PURPOSE: This profile is used by an AI system to score job postings for fit.

=== IDENTITY ===
Name: Your Full Name
Degree: MS Computer Science, University of XYZ — graduating May 2026
Visa Status: F-1 OPT — requires employer visa sponsorship (OPT/H-1B)
Work Authorization: USA only

=== EXPERIENCE ===
1. Company Name (Role)
   - What you built, shipped, or achieved
   ...

=== TECH STACK ===
Languages: Python, TypeScript, Java
...

=== SCORING CRITERIA ===
+2 if: LLM/AI/RAG integration is core to the role
+1 if: Python is primary language
-3 if: Requires 3+ years of experience
-3 if: Senior/Staff/Lead/Principal level role
-5 if: Intern, internship, co-op, or temporary trainee position
+1 if: Job explicitly mentions H1B/visa sponsorship
...
```

### 5. Add your base resume YAML

Create or convert your resume to [RenderCV YAML format](https://rendercv.com/user-guide/).
Save it as `base_resume.yaml` in the project root (or set `BASE_YAML_NAME` in `.env`) — **or upload it in the Setup tab**.

> To generate a RenderCV YAML from scratch: `python -m rendercv new "Your Name"` — this creates a template you can fill in.

### 6. Run the app

```powershell
# Option 1 — One-click (Windows)
start_app.bat

# Option 2 — Manual (two terminals)
python api/server.py              # Terminal 1: backend on :8000
cd frontend && npx next dev       # Terminal 2: frontend on :3000

# Option 3 — Legacy Streamlit
python -m streamlit run app.py
```

Open `http://localhost:3000` and click **Run Pipeline** to fetch and rank jobs.

---

## Running

### Option A — Next.js Dashboard (recommended)

**One-click:** double-click `start_app.bat` — it launches both servers and opens the browser.

**Manual start (two terminals):**

```powershell
# Terminal 1 — FastAPI backend
python api/server.py
```

```powershell
# Terminal 2 — Next.js frontend
cd frontend
npm install      # first time only
npx next dev
```

Opens at `http://localhost:3000`. Backend runs on `http://localhost:8000` (proxied automatically).

- **Dashboard** — AI-ranked top picks, stats, Run Pipeline / Refresh / Build All Resumes buttons
- **All Jobs** — search and browse every job from the latest run
- **Applied** — table of applied jobs
- **Generate Resume** — paste a JD, extract fields, generate a tailored PDF
- **Settings** — pipeline config, profile, resume YAML, API keys, Greenhouse companies, setup status

### Option B — Streamlit UI (legacy)

```powershell
python -m streamlit run app.py
```

Opens at `http://localhost:8501`.
- **Setup tab** — first-time config: enter profile, upload resume YAML, set API keys
- **Sidebar** — adjust keywords, filters, and AI settings; click **▶ Run Pipeline Now**
- **AI Top Picks** — ranked results with one-click apply + resume build
- **Generate Resume** — paste any job description to build a tailored PDF on demand

### Option C — Command line

```powershell
python src/run_pipeline.py
```

### Option D — Individual steps

```powershell
python src/fetch_jobs.py        # → output/raw_jobs.json
python src/filter_jobs.py       # → output/filtered_jobs.json
python src/dedupe_jobs.py       # → output/deduped_jobs.json
python src/save_to_sqlite.py    # → db/jobs.db
python src/ai_ranker.py         # → output/top25_jobs.json + scores in db/jobs.db
```

### Option E — Resume Builder (build tailored PDFs for each job)

```powershell
# Process all jobs in top25_jobs.json
python src/build_all_resumes.py

# Test with the first 3 jobs only
python src/build_all_resumes.py --limit 3

# Process one specific job by index (0-based)
python src/build_all_resumes.py --job 0

# Clear processed-jobs cache and re-run everything
python src/build_all_resumes.py --reset

# Clear cache and test with first 5 jobs
python src/build_all_resumes.py --reset --limit 5
```

Generated PDFs are saved to `resumes/{Company}_{Title}.pdf`. Jobs with no description are skipped. Already-processed jobs are skipped on re-runs unless `--reset` is passed.

---

## Daily Automation (Windows Task Scheduler)

Run once as Administrator to register the daily 8 AM job:

```powershell
powershell -ExecutionPolicy Bypass -File setup_scheduler.ps1
```

To verify or edit: open **Task Scheduler → Task Scheduler Library → JobHunterDailyCron**.

To remove the task:

```powershell
Unregister-ScheduledTask -TaskName "JobHunterDailyCron" -Confirm:$false
```

---

## Pipeline Flow

```
Sources
  └─ LinkedIn      (Apify actor + direct guest API — both run, results merged)  ─┐
  └─ Adzuna        (REST API)                                                      ├─→ raw_jobs.json
  └─ Greenhouse    (board API, company slugs from config.yaml)                    ─┘
         ↓
  filter_jobs.py
    • title keywords — keeps SE / AI / ML / backend / full-stack roles
    • seniority exclusion — drops Senior/Staff/Lead/Principal/Intern
    • experience exclusion — drops "3+ years" requirements
    • H1B negative filter — drops explicit no-sponsorship postings
    • location filter — US / remote only
    • date filter — within posted_within_hours window
         ↓
  dedupe_jobs.py  (url-exact + normalized company|title|location key)
         ↓
  save_to_sqlite.py  (UPSERT → db/jobs.db)
         ↓
  ai_ranker.py  (Azure OpenAI scores each job 1–10 → top N)
         ↓
  Next.js Dashboard  (Dashboard · All Jobs · Applied · Generate Resume · Settings)
  └─ or Streamlit UI (legacy)  (AI Top Picks · All Jobs · Applied · Generate Resume · Setup)
```

---

## AI Ranking

Each job is scored 1–10 against `profile.txt` using the criteria defined at the bottom of that file:

| Signal | Impact |
|---|---|
| LLM/AI/RAG core to role | +2 |
| Startup / AI-native company | +2 |
| Python primary language | +1 |
| Distributed systems / cloud | +1 |
| Entry-level / new grad stated | +1 |
| Explicitly mentions H1B/OPT/CPT sponsorship | +1 |
| All qualified applicants / we sponsor visas | +1 |
| Requires 3+ years experience | −3 |
| Senior/Staff/Lead/Principal | −3 |
| Intern / internship / co-op / trainee | −5 |
| No sponsorship / must be authorized | −3 |
| Requires citizenship or security clearance | −3 |
| Pure frontend only | −2 |
| Embedded/hardware/firmware | −2 |
| Sales engineering | −2 |

---

## Database Schema

**`jobs`** — one row per unique job URL

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER | Primary key |
| `source` | TEXT | linkedin, glassdoor, adzuna, greenhouse |
| `company` | TEXT | |
| `title` | TEXT | |
| `location` | TEXT | |
| `url` | TEXT UNIQUE | Dedup anchor |
| `description` | TEXT | |
| `posted_at` | TEXT | |
| `normalized_key` | TEXT | company\|title\|location |
| `status` | TEXT | new / reviewed |
| `run_date` | TEXT | UTC timestamp of pipeline run |
| `ai_score` | REAL | 1–10, NULL until ranked |
| `ai_reason` | TEXT | One-line AI explanation |

**`job_runs`** — one row per source per pipeline run

| Column | Type |
|---|---|
| `run_date` | TEXT |
| `source` | TEXT |
| `new_jobs` | INTEGER |
| `duplicate_jobs` | INTEGER |

---

## Customization

- **Add a new source:** Add a fetch function to `fetch_jobs.py` returning the normalized schema, then call it in `fetch_all()`.
- **Change AI model:** Update `azure_openai.deployment` in `config.yaml`.
- **Add Greenhouse companies:** Add slugs to `greenhouse_companies` in `config.yaml` (slug = the part of `https://boards.greenhouse.io/<slug>`).
- **Update your profile:** Edit `profile.txt` — the AI ranker reads it fresh on every run.
