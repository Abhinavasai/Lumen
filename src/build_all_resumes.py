"""
build_all_resumes.py
════════════════════════════════════════════════════════════════
Full automated pipeline:
  top25_jobs.json → GPT-4o tailors YAML → rendercv renders PDF
  → checks page count → trims if 2 pages → re-renders → saves

Usage:
    python build_all_resumes.py              # process all jobs
    python build_all_resumes.py --limit 5   # test with first 5 jobs
    python build_all_resumes.py --job 3     # process one specific job by index
"""

import os
import re
import sys
import glob
import json
import time
import shutil
import argparse
import subprocess
import tempfile
from datetime import datetime
import yaml
from dotenv import load_dotenv
from openai import OpenAI, AzureOpenAI

# ══════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════
BASE_DIR         = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS_FILE        = os.path.join(BASE_DIR, "output", "top25_jobs.json")
BASE_YAML        = os.path.join(BASE_DIR, os.getenv("BASE_YAML_NAME", "Abhinava_Sai_Tirunagari_CV.yaml"))
PROMPT_FILE      = os.path.join(BASE_DIR, "docs", "ATS_Resume_Tailoring_Prompt.txt")
PROJECTS_FILE    = os.path.join(BASE_DIR, "docs", "All_Projects.md")
OUTPUT_DIR       = os.path.join(BASE_DIR, "resumes")
DONE_LOG         = os.path.join(BASE_DIR, "output", ".processed_jobs.txt")
CONFIG_FILE      = os.path.join(BASE_DIR, "config.yaml")
MAX_TRIM_RETRIES = 3       # max render attempts per job before giving up
DELAY_BETWEEN    = 3       # seconds between jobs (avoid OpenAI rate limits)
DEBUG_DIR        = os.path.join(BASE_DIR, "output", "debug_resume_errors")
# ── Font-shrink levels: try smaller typography before asking GPT to trim content
# Base design: 7pt body, 0.35em line spacing, 0.3em entry spacing, 0.3cm section above
MAX_SHRINK_LEVELS = 3
SHRINK_LEVELS = [
    {"body_pt": 6.875, "line_spacing": 0.33, "entry_spacing": 0.28, "section_above": 0.28},
    {"body_pt": 6.75,  "line_spacing": 0.30, "entry_spacing": 0.25, "section_above": 0.25},
    {"body_pt": 6.625, "line_spacing": 0.28, "entry_spacing": 0.22, "section_above": 0.22},
]
# ══════════════════════════════════════════════════════════════

load_dotenv(os.path.join(BASE_DIR, ".env"))
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(DEBUG_DIR, exist_ok=True)


def build_client():
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        return OpenAI(api_key=openai_key), "gpt-4o", "openai"

    if not os.path.exists(CONFIG_FILE):
        raise RuntimeError(f"Missing config file: {CONFIG_FILE}")

    with open(CONFIG_FILE, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    azure_cfg = cfg.get("azure_openai", {})
    endpoint = azure_cfg.get("endpoint")
    deployment = azure_cfg.get("deployment")
    # Responses API for this Azure setup requires 2025-03-01-preview or later.
    api_version = "2025-03-01-preview"
    api_key = os.getenv("AZURE_OPENAI_API_KEY")

    if not endpoint or not deployment or not api_key:
        raise RuntimeError(
            "Azure config is incomplete. Set azure_openai in config.yaml and AZURE_OPENAI_API_KEY in .env."
        )

    return (
        AzureOpenAI(azure_endpoint=endpoint, api_key=api_key, api_version=api_version),
        deployment,
        "azure",
    )


client, MODEL_NAME, PROVIDER = build_client()


# ────────────────────────────────────────────────────────────
#  HELPERS
# ────────────────────────────────────────────────────────────

def load_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def save_file(path: str, content: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def validate_yaml_text(yaml_text: str) -> tuple[bool, str]:
    try:
        yaml.safe_load(yaml_text)
        return True, ""
    except Exception as e:
        return False, str(e)


def sanitize_rendercv_yaml(yaml_text: str) -> str:
    """
    Remove fields that RenderCV's schema doesn't support at the cv level.
    GPT sometimes adds 'summary:' under cv: — that causes a validation error.
    """
    try:
        data = yaml.safe_load(yaml_text)
        if isinstance(data, dict) and "cv" in data:
            data["cv"].pop("summary", None)
        return yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)
    except Exception:
        return yaml_text  # if parsing fails, return as-is (validator will catch it)


def apply_shrink_level(yaml_text: str, level: int) -> str:
    """Reduce font size and spacing to fit content on fewer pages.
    Level 1 = slight shrink (8.25pt), level 4 = max shrink (7.5pt)."""
    if level < 1 or level > len(SHRINK_LEVELS):
        return yaml_text
    cfg = SHRINK_LEVELS[level - 1]
    data = yaml.safe_load(yaml_text)
    design = data.get("design", {})
    typo = design.get("typography", {})
    fs = typo.get("font_size", {})
    sects = design.get("sections", {})
    stit = design.get("section_titles", {})

    fs["body"] = f"{cfg['body_pt']}pt"
    typo["line_spacing"] = f"{cfg['line_spacing']}em"
    typo["font_size"] = fs
    sects["space_between_regular_entries"] = f"{cfg['entry_spacing']}em"
    stit["space_above"] = f"{cfg['section_above']}cm"

    design["typography"] = typo
    design["sections"] = sects
    design["section_titles"] = stit
    data["design"] = design
    return yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)


def job_id(job: dict) -> str:
    company = job.get("company", job.get("companyName", "Company")).strip()
    title   = job.get("title", job.get("position", "Role")).strip()
    return f"{company}_{title}".replace("/", "-").replace(" ", "_")


def safe_name(text: str) -> str:
    return re.sub(r'[^\w\-]', '_', text.strip())


def load_done() -> set:
    if not os.path.exists(DONE_LOG):
        return set()
    with open(DONE_LOG, encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())


def mark_done(jid: str):
    with open(DONE_LOG, "a", encoding="utf-8") as f:
        f.write(jid + "\n")


# ────────────────────────────────────────────────────────────
#  STEP 1 — CALL GPT-4o TO TAILOR THE YAML
# ────────────────────────────────────────────────────────────

def tailor_yaml(job: dict, base_yaml: str, tailoring_prompt: str,
                projects_pool: str = "", trim_note: str = "") -> str:
    """
    Send the job description + base YAML + project pool + ATS prompt to GPT-4o.
    Returns a tailored YAML string.
    trim_note is appended when we need GPT to shorten for page count.
    projects_pool is the full All_Projects.md content for project selection.
    """
    company     = job.get("company", job.get("companyName", "Company")).strip()
    title       = job.get("title", job.get("position", "Role")).strip()
    location    = job.get("location", "N/A")
    description = job.get("description", job.get("descriptionText", "")).strip()

    projects_section = ""
    if projects_pool:
        projects_section = f"""
════════════════════════════════
FULL PROJECT PORTFOLIO (select from these)
════════════════════════════════
{projects_pool}
"""

    user_message = f"""
{tailoring_prompt}

════════════════════════════════
JOB DETAILS
════════════════════════════════
Title    : {title}
Company  : {company}
Location : {location}

Job Description:
{description[:4000]}

════════════════════════════════
BASE RESUME YAML
════════════════════════════════
{base_yaml}
{projects_section}
════════════════════════════════
OUTPUT INSTRUCTIONS
════════════════════════════════
Return ONLY the complete, valid YAML — no explanation, no markdown code fences, no preamble.
The YAML must be rendercv-compatible and maintain the exact same structure as the base resume.
{trim_note}
"""

    if PROVIDER == "azure":
        response = client.responses.create(
            model=MODEL_NAME,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert ATS resume optimizer. "
                        "You output only raw valid YAML - no markdown, no explanation, no code fences. "
                        "Never use ': ' (colon + space) mid-sentence in YAML bullet strings."
                    )
                },
                {"role": "user", "content": user_message},
            ],
        )
        raw = (response.output_text or "").strip()
    else:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert ATS resume optimizer. "
                        "You output only raw valid YAML - no markdown, no explanation, no code fences. "
                        "Never use ': ' (colon + space) mid-sentence in YAML bullet strings."
                    )
                },
                {"role": "user", "content": user_message}
            ],
            temperature=0.2,
        )
        raw = (response.choices[0].message.content or "").strip()

    # Strip accidental markdown fences if GPT adds them
    raw = re.sub(r'^```ya?ml\s*', '', raw, flags=re.IGNORECASE)
    raw = re.sub(r'\s*```$', '', raw)

    return raw.strip()


# ────────────────────────────────────────────────────────────
#  STEP 2 — RENDER PDF WITH rendercv
# ────────────────────────────────────────────────────────────

def render_pdf(yaml_path: str, pdf_path: str) -> tuple[bool, str]:
    """
    Runs rendercv render on the yaml file.
    Returns (success, error_message).
    rendercv outputs files into a subfolder — we move the PDF to pdf_path.
    """
    render_dir = os.path.splitext(yaml_path)[0] + "__render"
    if os.path.isdir(render_dir):
        shutil.rmtree(render_dir, ignore_errors=True)
    os.makedirs(render_dir, exist_ok=True)

    result = subprocess.run(
        [sys.executable, "-m", "rendercv", "render", yaml_path, "--output-folder", render_dir],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={
            **os.environ,
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        },
    )

    if result.returncode != 0:
        err_text = (result.stderr or "").strip()
        out_text = (result.stdout or "").strip()
        if out_text:
            err_text = f"{err_text}\n{out_text}".strip()
        if not err_text:
            err_text = "rendercv exited non-zero without stderr/stdout output."
        return False, err_text[:800]

    generated_pdfs = glob.glob(os.path.join(render_dir, "**", "*.pdf"), recursive=True)
    generated_pdfs = sorted(generated_pdfs, key=os.path.getmtime, reverse=True)

    if not generated_pdfs:
        return False, "rendercv finished but no PDF was found in output artifacts."

    try:
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
        shutil.copy2(generated_pdfs[0], pdf_path)
    except Exception as e:
        return False, f"Failed to copy rendered PDF: {e}"

    if not os.path.exists(pdf_path):
        return False, "Failed to copy rendered PDF to target path."

    return True, ""


# ────────────────────────────────────────────────────────────
#  STEP 3 — COUNT PAGES (via PNG output from rendercv)
# ────────────────────────────────────────────────────────────

def count_pages(pdf_path: str) -> int:
    """
    Count pages from rendered PDF bytes.
    We intentionally avoid falling back to 1 so trim logic is not skipped silently.
    """
    if not os.path.exists(pdf_path):
        return 0

    try:
        with open(pdf_path, "rb") as f:
            data = f.read()
        # Count PDF page objects (matches /Type /Page but not /Pages)
        return len(re.findall(rb"/Type\s*/Page\b", data))
    except Exception:
        return 0


# ────────────────────────────────────────────────────────────
#  STEP 4 — FULL JOB PROCESSOR (tailor → render → trim loop)
# ────────────────────────────────────────────────────────────

def build_trim_note(pages: int, attempt: int) -> str:
    """Progressive trim guidance after font shrinking has already been tried."""
    min_pt = SHRINK_LEVELS[-1]["body_pt"]
    common = f"""
IMPORTANT - PAGE COUNT ISSUE:
The previous version rendered as {pages} pages, even after reducing font to {min_pt}pt.
Font reduction will be applied automatically after you produce the YAML.
Your goal: trim content so it fits on 1 WELL-FILLED page at 7pt body font size.
Minor overflow (~10-15%) is OK — font shrinking will handle it automatically.
- Do NOT over-trim: the page should be 90-95% filled at 7pt, not sparse with empty space.
- Preserve JD-aligned keywords and measurable outcomes.
- Do not change company names, dates, institutions, or GPA.
- Keep ALL 5 experience entries — NEVER remove an experience.
- Do NOT add an Extracurricular Activities section.
- Use design: body font 7pt, name 14pt bold, section_titles 1.0em bold, 0.35em line spacing, 0.3em entry spacing, 0.8cm margins.
"""

    if attempt == 1:
        return common + """
MODERATE trim — reduce content slightly, font shrinking handles the rest:
1) Make each bullet 1-2 concise lines (no 3-line bullets).
2) Reduce projects from 6 to 5, each with 2 compact bullets.
3) Shorten Summary to 2 sentences if it's currently 3.
4) Trim project technology tags to 6-8 most relevant technologies.
5) Remove filler phrases and replace with JD keyword-rich specifics.
6) Reduce ADRIN-ISRO to 2 bullets and INRY to 1 bullet.
Remember: minor overflow is handled by font shrinking — do NOT trim below 90% page fill at 7pt.
MANDATORY: keep all 5 experiences, minimum 5 projects, no extracurriculars.
"""
    if attempt == 2:
        return common + """
FIRMER trim — target well-filled 1 page, NOT a sparse page:
1) UF and Cognera: 2 bullets each, each 1 line.
2) ADP: 2 bullets, each 1 line.
3) ADRIN-ISRO: 2 bullets, 1 line each. INRY: 1 bullet, 1 line.
4) Projects: 5 projects, each with 1-2 bullets.
5) Compress project technology tags to 5-6 key technologies.
6) Shorten Summary to 2 sentences.
MANDATORY: keep all 5 experiences, minimum 5 projects, no extracurriculars.
Minimum content floor: Summary >= 1 bullet, UF >= 2, Cognera >= 2, ADP >= 2, ISRO >= 1, INRY >= 1, Projects >= 5.
"""
    return common + """
AGGRESSIVE trim — but still aim for a FULL page, not a sparse one:
1) Summary: 2 sentences.
2) UF and Cognera: 2 compact bullets (1 line each).
3) ADP: 2 compact bullets (1 line each).
4) ADRIN-ISRO: 1 bullet. INRY: 1 bullet.
5) Projects: exactly 5 projects with 1 short bullet each.
MANDATORY: keep all 5 experiences, minimum 5 projects, no extracurriculars.
Every bullet must contain at least 1 JD keyword.
"""


def process_job(job: dict, base_yaml: str, tailoring_prompt: str,
                projects_pool: str, index: int) -> bool:
    company  = safe_name(job.get("company", job.get("companyName", "Company")))
    title    = safe_name(job.get("title", job.get("position", "Role")))
    jid      = f"{company}_{title}"
    pdf_out  = os.path.join(OUTPUT_DIR, f"{jid}.pdf")
    working_pdf_out = os.path.join(OUTPUT_DIR, f"{jid}__working.pdf")
    first_attempt_pdf = os.path.join(OUTPUT_DIR, f"{jid}__attempt1.pdf")
    temp_yaml_path = None

    print(f"\n{'-'*60}")
    print(f"[{index}] {job.get('title')} @ {job.get('company', job.get('companyName'))}")
    print(f"{'-'*60}")

    trim_note = ""
    MAX_YAML_RETRIES = 2   # extra API retries when model outputs invalid YAML

    for attempt in range(1, MAX_TRIM_RETRIES + 1):
        # ── Tailor YAML via GPT-4o (with YAML-validity retries) ──
        tailored = None
        yaml_err = ""
        for yaml_attempt in range(1, MAX_YAML_RETRIES + 2):
            label = f"(trimming attempt {attempt})" if attempt > 1 else ""
            retry_label = f", YAML retry {yaml_attempt}" if yaml_attempt > 1 else ""
            print(f"   GPT tailoring {label}{retry_label}...", end="", flush=True)
            extra_note = trim_note
            if yaml_attempt > 1:
                extra_note += f"""

CRITICAL — Your previous response was not valid YAML.
Error: {yaml_err}
Common causes:
- Merging two keys onto the same line (e.g. `position: "Foo  end_date: 2025"`)
- Unquoted colon in a value string (use double quotes around any value containing ': ')
- Unclosed quote in a string value
Output ONLY raw valid YAML — nothing else. Double-check every line before responding.
"""
            try:
                tailored = tailor_yaml(job, base_yaml, tailoring_prompt, projects_pool, extra_note)
            except Exception as e:
                print(f" [ERROR] OpenAI error: {e}")
                return False
            print(" [OK]")
            is_valid_yaml, yaml_err = validate_yaml_text(tailored)
            if is_valid_yaml:
                tailored = sanitize_rendercv_yaml(tailored)
                break
            debug_yaml = os.path.join(DEBUG_DIR, f"{jid}_attempt{attempt}_yamlretry{yaml_attempt}_invalid.yaml")
            save_file(debug_yaml, tailored)
            print(f"   [WARN] Invalid YAML (retry {yaml_attempt}/{MAX_YAML_RETRIES}): {yaml_err[:120]}")

        if not is_valid_yaml:
            print(f" [ERROR] Model produced invalid YAML after {MAX_YAML_RETRIES + 1} tries: {yaml_err}")
            if attempt > 1 and os.path.exists(first_attempt_pdf):
                final_pdf_path = pdf_out
                if os.path.exists(final_pdf_path):
                    try:
                        os.remove(final_pdf_path)
                    except Exception:
                        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                        final_pdf_path = os.path.join(OUTPUT_DIR, f"{jid}_{ts}.pdf")
                shutil.copy2(first_attempt_pdf, final_pdf_path)
                print(f" [WARN] Using attempt-1 PDF fallback: {final_pdf_path}")
                if os.path.exists(first_attempt_pdf):
                    os.remove(first_attempt_pdf)
                return True
            return False

        # ── Save tailored YAML ──────────────────────────────
        if not temp_yaml_path:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".yaml",
                prefix=f"{jid}_",
                dir=OUTPUT_DIR,
                delete=False,
                encoding="utf-8",
            ) as tmp:
                temp_yaml_path = tmp.name
        save_file(temp_yaml_path, tailored)

        # ── Render PDF ──────────────────────────────────────
        print(f"   Rendering PDF (attempt {attempt})...", end="", flush=True)
        ok, err = render_pdf(temp_yaml_path, working_pdf_out)
        if not ok:
            print(f" [ERROR] rendercv error: {err}")
            debug_yaml = os.path.join(DEBUG_DIR, f"{jid}_attempt{attempt}_render_fail.yaml")
            if temp_yaml_path and os.path.exists(temp_yaml_path):
                shutil.copy2(temp_yaml_path, debug_yaml)
                print(f" [DEBUG] Saved failed YAML: {debug_yaml}")
            if attempt > 1 and os.path.exists(first_attempt_pdf):
                final_pdf_path = pdf_out
                if os.path.exists(final_pdf_path):
                    try:
                        os.remove(final_pdf_path)
                    except Exception:
                        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                        final_pdf_path = os.path.join(OUTPUT_DIR, f"{jid}_{ts}.pdf")
                shutil.copy2(first_attempt_pdf, final_pdf_path)
                print(f" [WARN] Using attempt-1 PDF fallback: {final_pdf_path}")
                if os.path.exists(first_attempt_pdf):
                    os.remove(first_attempt_pdf)
                if temp_yaml_path and os.path.exists(temp_yaml_path):
                    os.remove(temp_yaml_path)
                if os.path.exists(working_pdf_out):
                    os.remove(working_pdf_out)
                temp_render_dir = os.path.splitext(temp_yaml_path)[0]
                temp_render_output_dir = f"{temp_render_dir}__render"
                if os.path.isdir(temp_render_dir):
                    shutil.rmtree(temp_render_dir, ignore_errors=True)
                if os.path.isdir(temp_render_output_dir):
                    shutil.rmtree(temp_render_output_dir, ignore_errors=True)
                return True
            if temp_yaml_path and os.path.exists(temp_yaml_path):
                os.remove(temp_yaml_path)
            if os.path.exists(working_pdf_out):
                os.remove(working_pdf_out)
            temp_render_dir = os.path.splitext(temp_yaml_path)[0]
            temp_render_output_dir = f"{temp_render_dir}__render"
            if os.path.isdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)
            if os.path.isdir(temp_render_output_dir):
                shutil.rmtree(temp_render_output_dir, ignore_errors=True)
            return False
        print(" [OK]")

        # ── Check page count ────────────────────────────────
        pages = count_pages(working_pdf_out)
        print(f"   Page count: {pages}")

        if attempt == 1 and pages > 1 and os.path.exists(working_pdf_out):
            try:
                shutil.copy2(working_pdf_out, first_attempt_pdf)
            except Exception:
                pass

        if pages <= 0:
            print(" [ERROR] Could not determine PDF page count.")
            debug_yaml = os.path.join(DEBUG_DIR, f"{jid}_attempt{attempt}_pagecount_fail.yaml")
            if temp_yaml_path and os.path.exists(temp_yaml_path):
                shutil.copy2(temp_yaml_path, debug_yaml)
                print(f" [DEBUG] Saved failed YAML: {debug_yaml}")
            if attempt > 1 and os.path.exists(first_attempt_pdf):
                final_pdf_path = pdf_out
                if os.path.exists(final_pdf_path):
                    try:
                        os.remove(final_pdf_path)
                    except Exception:
                        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                        final_pdf_path = os.path.join(OUTPUT_DIR, f"{jid}_{ts}.pdf")
                shutil.copy2(first_attempt_pdf, final_pdf_path)
                print(f" [WARN] Using attempt-1 PDF fallback: {final_pdf_path}")
                if os.path.exists(first_attempt_pdf):
                    os.remove(first_attempt_pdf)
                if temp_yaml_path and os.path.exists(temp_yaml_path):
                    os.remove(temp_yaml_path)
                if os.path.exists(working_pdf_out):
                    os.remove(working_pdf_out)
                temp_render_dir = os.path.splitext(temp_yaml_path)[0]
                temp_render_output_dir = f"{temp_render_dir}__render"
                if os.path.isdir(temp_render_dir):
                    shutil.rmtree(temp_render_dir, ignore_errors=True)
                if os.path.isdir(temp_render_output_dir):
                    shutil.rmtree(temp_render_output_dir, ignore_errors=True)
                return True
            if temp_yaml_path and os.path.exists(temp_yaml_path):
                os.remove(temp_yaml_path)
            if os.path.exists(working_pdf_out):
                os.remove(working_pdf_out)
            temp_render_dir = os.path.splitext(temp_yaml_path)[0]
            temp_render_output_dir = f"{temp_render_dir}__render"
            if os.path.isdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)
            if os.path.isdir(temp_render_output_dir):
                shutil.rmtree(temp_render_output_dir, ignore_errors=True)
            return False

        if pages == 1:
            final_pdf_path = pdf_out
            if os.path.exists(final_pdf_path):
                try:
                    os.remove(final_pdf_path)
                except Exception:
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    final_pdf_path = os.path.join(OUTPUT_DIR, f"{jid}_{ts}.pdf")
            try:
                shutil.move(working_pdf_out, final_pdf_path)
            except Exception as e:
                print(f" [ERROR] Could not finalize PDF: {e}")
                if temp_yaml_path and os.path.exists(temp_yaml_path):
                    os.remove(temp_yaml_path)
                temp_render_dir = os.path.splitext(temp_yaml_path)[0]
                if os.path.isdir(temp_render_dir):
                    shutil.rmtree(temp_render_dir, ignore_errors=True)
                return False
            print(f"   [OK] Single page achieved in {attempt} attempt(s)!")
            print(f"   Saved: {final_pdf_path}")
            if temp_yaml_path and os.path.exists(temp_yaml_path):
                os.remove(temp_yaml_path)
            if os.path.exists(first_attempt_pdf):
                os.remove(first_attempt_pdf)
            temp_render_dir = os.path.splitext(temp_yaml_path)[0]
            temp_render_output_dir = f"{temp_render_dir}__render"
            if os.path.isdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)
            if os.path.isdir(temp_render_output_dir):
                shutil.rmtree(temp_render_output_dir, ignore_errors=True)
            return True

        # ── Too many pages — try font shrinking before content trim ──
        print(f"   [INFO] {pages} pages at original font — trying font reduction...")
        font_fitted = False
        for shrink_level in range(1, MAX_SHRINK_LEVELS + 1):
            body_pt = SHRINK_LEVELS[shrink_level - 1]["body_pt"]
            shrunk_yaml = apply_shrink_level(tailored, shrink_level)
            save_file(temp_yaml_path, shrunk_yaml)
            print(f"   Rendering at {body_pt}pt (shrink {shrink_level}/{MAX_SHRINK_LEVELS})...", end="", flush=True)
            ok_s, err_s = render_pdf(temp_yaml_path, working_pdf_out)
            if not ok_s:
                print(f" [ERROR] {err_s}")
                break
            pages = count_pages(working_pdf_out)
            print(f" {pages} page(s)")
            if pages == 1:
                font_fitted = True
                break

        if font_fitted:
            final_pdf_path = pdf_out
            if os.path.exists(final_pdf_path):
                try:
                    os.remove(final_pdf_path)
                except Exception:
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    final_pdf_path = os.path.join(OUTPUT_DIR, f"{jid}_{ts}.pdf")
            try:
                shutil.move(working_pdf_out, final_pdf_path)
            except Exception as e:
                print(f" [ERROR] Could not finalize PDF: {e}")
                if temp_yaml_path and os.path.exists(temp_yaml_path):
                    os.remove(temp_yaml_path)
                temp_render_dir = os.path.splitext(temp_yaml_path)[0]
                temp_render_output_dir = f"{temp_render_dir}__render"
                if os.path.isdir(temp_render_dir):
                    shutil.rmtree(temp_render_dir, ignore_errors=True)
                if os.path.isdir(temp_render_output_dir):
                    shutil.rmtree(temp_render_output_dir, ignore_errors=True)
                return False
            print(f"   [OK] Single page at {body_pt}pt (shrink level {shrink_level}, attempt {attempt})!")
            print(f"   Saved: {final_pdf_path}")
            if temp_yaml_path and os.path.exists(temp_yaml_path):
                os.remove(temp_yaml_path)
            if os.path.exists(first_attempt_pdf):
                os.remove(first_attempt_pdf)
            temp_render_dir = os.path.splitext(temp_yaml_path)[0]
            temp_render_output_dir = f"{temp_render_dir}__render"
            if os.path.isdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)
            if os.path.isdir(temp_render_output_dir):
                shutil.rmtree(temp_render_output_dir, ignore_errors=True)
            return True

        # ── Font at minimum, still too long — fall back to content trim ──
        if attempt < MAX_TRIM_RETRIES:
            min_pt = SHRINK_LEVELS[-1]["body_pt"]
            print(f"   [WARN] Still {pages} pages at {min_pt}pt — asking GPT to trim content...")
            trim_note = build_trim_note(pages, attempt)
        else:
            final_pdf_path = pdf_out
            if os.path.exists(final_pdf_path):
                try:
                    os.remove(final_pdf_path)
                except Exception:
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    final_pdf_path = os.path.join(OUTPUT_DIR, f"{jid}_{ts}.pdf")
            if os.path.exists(working_pdf_out):
                try:
                    shutil.move(working_pdf_out, final_pdf_path)
                except Exception:
                    pass
            print(f"   [WARN] Could not achieve single page after {MAX_TRIM_RETRIES} attempts + font shrinking — saving best version")
            if temp_yaml_path and os.path.exists(temp_yaml_path):
                os.remove(temp_yaml_path)
            if os.path.exists(first_attempt_pdf):
                os.remove(first_attempt_pdf)
            temp_render_dir = os.path.splitext(temp_yaml_path)[0]
            temp_render_output_dir = f"{temp_render_dir}__render"
            if os.path.isdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)
            if os.path.isdir(temp_render_output_dir):
                shutil.rmtree(temp_render_output_dir, ignore_errors=True)
            return True  # Save what we have

    return True


# ────────────────────────────────────────────────────────────
#  MAIN — loop all jobs
# ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit",      type=int,   default=None, help="Process only first N jobs (for testing)")
    parser.add_argument("--job",        type=int,   default=None, help="Process one specific job by index")
    parser.add_argument("--reset",      action="store_true",      help="Clear processed-jobs cache before running")
    parser.add_argument("--jobs-file",  type=str,   default=None, help="Path to a custom jobs JSON file (overrides default)")
    args = parser.parse_args()

    if args.reset and os.path.exists(DONE_LOG):
        os.remove(DONE_LOG)
        print("[RESET] Cleared processed-jobs cache.\n")

    jobs_file = args.jobs_file if args.jobs_file else JOBS_FILE

    # ── Load inputs ─────────────────────────────────────────
    print("Resume Pipeline Starting...")
    print(f"   Provider    : {PROVIDER}")
    print(f"   Model       : {MODEL_NAME}")
    print(f"   Jobs file   : {jobs_file}")
    print(f"   Base YAML   : {BASE_YAML}")
    print(f"   Prompt file : {PROMPT_FILE}")
    print(f"   Projects    : {PROJECTS_FILE}")
    print(f"   Output dir  : {OUTPUT_DIR}/\n")

    for f in [jobs_file, BASE_YAML, PROMPT_FILE]:
        if not os.path.exists(f):
            print(f"[ERROR] Missing file: {f}")
            return

    with open(jobs_file, encoding="utf-8") as f:
        jobs = json.load(f)

    base_yaml        = load_file(BASE_YAML)
    tailoring_prompt = load_file(PROMPT_FILE)
    projects_pool    = load_file(PROJECTS_FILE) if os.path.exists(PROJECTS_FILE) else ""
    if not projects_pool:
        print("[WARN] All_Projects.md not found — GPT will only use projects from base YAML.")
    done             = load_done()

    # ── Apply filters ────────────────────────────────────────
    if args.job is not None:
        jobs = [jobs[args.job]]
    elif args.limit:
        jobs = jobs[:args.limit]

    total     = len(jobs)
    success   = 0
    skipped   = 0
    failed    = 0
    start     = datetime.now()

    print(f"Jobs to process: {total} | Already done: {len(done)}\n")

    for i, job in enumerate(jobs, 1):
        jid = job_id(job)

        # Skip already processed
        if jid in done:
            print(f"[{i}/{total}] Skipping (already done): {jid}")
            skipped += 1
            continue

        # Skip if no description
        description = job.get("description", job.get("descriptionText", "")).strip()
        if not description:
            print(f"[{i}/{total}] Skipping (no description): {jid}")
            mark_done(jid)
            skipped += 1
            continue

        # Process the job
        ok = process_job(job, base_yaml, tailoring_prompt, projects_pool, f"{i}/{total}")

        if ok:
            mark_done(jid)
            done.add(jid)
            success += 1
        else:
            failed += 1

        # Rate limit buffer between jobs
        if i < total:
            time.sleep(DELAY_BETWEEN)

    # ── Summary ──────────────────────────────────────────────
    elapsed = (datetime.now() - start).seconds
    print(f"\n{'='*60}")
    print(f"Pipeline complete!")
    print(f"   Success : {success}")
    print(f"   Skipped : {skipped}")
    print(f"   Failed  : {failed}")
    print(f"   Time    : {elapsed//60}m {elapsed%60}s")
    print(f"   PDFs    : ./{OUTPUT_DIR}/")
    print(f"{'='*60}")


def build_all():
    """Pipeline-callable entry point (no argparse)."""
    jobs_file = JOBS_FILE
    if not os.path.exists(jobs_file):
        print(f"[build_all] No jobs file found at {jobs_file} — skipping resume build.")
        return

    for f in [BASE_YAML, PROMPT_FILE]:
        if not os.path.exists(f):
            print(f"[ERROR] Missing file: {f}")
            return

    with open(jobs_file, encoding="utf-8") as f:
        jobs = json.load(f)

    base_yaml = load_file(BASE_YAML)
    tailoring_prompt = load_file(PROMPT_FILE)
    projects_pool = load_file(PROJECTS_FILE) if os.path.exists(PROJECTS_FILE) else ""
    done = load_done()

    total = len(jobs)
    success = 0
    skipped = 0
    failed = 0

    print(f"[build_all] Jobs to process: {total} | Already done: {len(done)}\n")

    for i, job in enumerate(jobs, 1):
        jid = job_id(job)
        if jid in done:
            skipped += 1
            continue
        description = job.get("description", job.get("descriptionText", "")).strip()
        if not description:
            mark_done(jid)
            skipped += 1
            continue
        ok = process_job(job, base_yaml, tailoring_prompt, projects_pool, f"{i}/{total}")
        if ok:
            mark_done(jid)
            done.add(jid)
            success += 1
        else:
            failed += 1
        if i < total:
            time.sleep(DELAY_BETWEEN)

    print(f"[build_all] Done — success={success} skipped={skipped} failed={failed}")


if __name__ == "__main__":
    main()
