"""
auto_apply.py
Automated job application submission for Greenhouse, Ashby, and Lever platforms.
Reads from top25_jobs.json (or SQLite), matches PDFs, and submits applications.
Greenhouse jobs that require email verification use Gmail IMAP to read codes.

Usage:
    python auto_apply.py                   # apply to all unapplied ranked jobs
    python auto_apply.py --dry-run         # preview what would be submitted
    python auto_apply.py --source ashby    # only apply to ashby jobs
"""
import argparse
import imaplib
import email as email_lib
import json
import os
import re
import sqlite3
import time
from datetime import datetime, timedelta
from email.header import decode_header

import requests
import yaml
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# ── Path resolution ─────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
DB_DIR = os.path.join(BASE_DIR, "db")
DB_PATH = os.path.join(DB_DIR, "jobs.db")
RANKED_JOBS = os.path.join(OUTPUT_DIR, "top25_jobs.json")
PROFILE_PATH = os.path.join(BASE_DIR, "profile.txt")

load_dotenv(os.path.join(BASE_DIR, ".env"))

# ── Candidate info (loaded from env) ────────────────────────────────────────
CANDIDATE = {
    "first_name": os.getenv("CANDIDATE_FIRST_NAME", ""),
    "last_name": os.getenv("CANDIDATE_LAST_NAME", ""),
    "email": os.getenv("CANDIDATE_EMAIL", ""),
    "phone": os.getenv("CANDIDATE_PHONE", ""),
    "linkedin": os.getenv("CANDIDATE_LINKEDIN", ""),
    "github": os.getenv("CANDIDATE_GITHUB", ""),
    "website": os.getenv("CANDIDATE_WEBSITE", ""),
    "location": os.getenv("CANDIDATE_LOCATION", ""),
}

GMAIL_USER = os.getenv("GMAIL_USER", CANDIDATE["email"])
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def safe_name(text: str) -> str:
    return re.sub(r"[^\w\-]", "_", text.strip())


def load_config():
    with open(os.path.join(BASE_DIR, "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


# ═══════════════════════════════════════════════════════════════════════════
#  DATABASE HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def init_db(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS applied_jobs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            source_job_id   TEXT UNIQUE,
            title           TEXT,
            company         TEXT,
            url             TEXT,
            applied_at      TEXT,
            platform        TEXT,
            status          TEXT DEFAULT 'submitted',
            error           TEXT
        )
    """)
    existing = {row[1] for row in conn.execute("PRAGMA table_info(applied_jobs)").fetchall()}
    for col, default in [("platform", "''"), ("status", "'submitted'"), ("error", "''")]:
        if col not in existing:
            conn.execute(f"ALTER TABLE applied_jobs ADD COLUMN {col} TEXT DEFAULT {default}")
    conn.commit()


def is_already_applied(conn: sqlite3.Connection, url: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM applied_jobs WHERE url = ? AND status = 'submitted'", (url,)
    ).fetchone()
    return row is not None


def record_application(conn: sqlite3.Connection, job: dict, platform: str,
                       status: str = "submitted", error: str = ""):
    try:
        conn.execute(
            """INSERT INTO applied_jobs
               (source_job_id, title, company, url, applied_at, platform, status, error)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(source_job_id) DO UPDATE SET
                   status = excluded.status,
                   applied_at = excluded.applied_at,
                   error = excluded.error
            """,
            (
                job.get("source_job_id", ""),
                job.get("title", ""),
                job.get("company", ""),
                job.get("url", ""),
                datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                platform,
                status,
                error,
            ),
        )
        conn.commit()
    except sqlite3.Error as e:
        print(f"  [DB] Error recording application: {e}")


# ═══════════════════════════════════════════════════════════════════════════
#  RESUME MATCHING
# ═══════════════════════════════════════════════════════════════════════════

RESUME_DIR = os.path.join(BASE_DIR, "resumes")


def find_resume_pdf(job: dict) -> str | None:
    company = safe_name(job.get("company", job.get("companyName", "Company")))
    title = safe_name(job.get("title", job.get("position", "Role")))
    jid = f"{company}_{title}"
    for search_dir in (RESUME_DIR, OUTPUT_DIR):
        if not os.path.isdir(search_dir):
            continue
        pdf_path = os.path.join(search_dir, f"{jid}.pdf")
        if os.path.exists(pdf_path):
            return pdf_path
        for fname in os.listdir(search_dir):
            if fname.endswith(".pdf") and company.lower() in fname.lower():
                return os.path.join(search_dir, fname)
    return None


# ═══════════════════════════════════════════════════════════════════════════
#  GMAIL IMAP — VERIFICATION CODE READER
# ═══════════════════════════════════════════════════════════════════════════

def connect_gmail() -> imaplib.IMAP4_SSL | None:
    if not GMAIL_APP_PASSWORD:
        print("  [Gmail] GMAIL_APP_PASSWORD not set — cannot read verification codes")
        return None
    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        imap.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        return imap
    except imaplib.IMAP4.error as e:
        print(f"  [Gmail] Login failed: {e}")
        return None


def fetch_verification_code(imap: imaplib.IMAP4_SSL, sender_pattern: str = "greenhouse",
                            max_wait_secs: int = 90, poll_interval: int = 10) -> str | None:
    cutoff = datetime.utcnow() - timedelta(minutes=5)
    date_str = cutoff.strftime("%d-%b-%Y")

    for attempt in range(max_wait_secs // poll_interval):
        imap.select("INBOX")
        search_query = f'(SINCE "{date_str}" UNSEEN)'
        _, msg_ids = imap.search(None, search_query)
        if not msg_ids[0]:
            time.sleep(poll_interval)
            continue

        for msg_id in reversed(msg_ids[0].split()):
            _, msg_data = imap.fetch(msg_id, "(RFC822)")
            raw_email = msg_data[0][1]
            msg = email_lib.message_from_bytes(raw_email)

            from_addr = msg.get("From", "").lower()
            subject = ""
            raw_subject = msg.get("Subject", "")
            if raw_subject:
                decoded_parts = decode_header(raw_subject)
                subject = "".join(
                    part.decode(enc or "utf-8") if isinstance(part, bytes) else part
                    for part, enc in decoded_parts
                )

            if sender_pattern.lower() not in from_addr and sender_pattern.lower() not in subject.lower():
                continue

            body = _extract_email_body(msg)
            code = _extract_code_from_text(body)
            if code:
                imap.store(msg_id, "+FLAGS", "\\Seen")
                return code

        time.sleep(poll_interval)

    return None


def _extract_email_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode("utf-8", errors="replace")
            elif ct == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    soup = BeautifulSoup(payload.decode("utf-8", errors="replace"), "html.parser")
                    return soup.get_text(separator=" ")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode("utf-8", errors="replace")
    return ""


def _extract_code_from_text(text: str) -> str | None:
    patterns = [
        r"(?:verification|confirm|code|pin|otp)[:\s]*(\d{4,8})",
        r"(\d{4,8})\s*(?:is your|verification|code|confirm)",
        r"\b(\d{6})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


# ═══════════════════════════════════════════════════════════════════════════
#  ASHBY APPLIER — REST API
# ═══════════════════════════════════════════════════════════════════════════

def _extract_ashby_slug_and_id(job: dict) -> tuple[str, str]:
    url = job.get("url", "")
    match = re.search(r"ashbyhq\.com/([^/]+)/[^/]*?([a-f0-9\-]{36})", url)
    if match:
        return match.group(1), match.group(2)
    return job.get("company", ""), job.get("source_job_id", "")


ASHBY_GQL = "https://jobs.ashbyhq.com/api/non-user-graphql"


def get_ashby_form(slug: str, posting_id: str) -> dict | None:
    query = (
        "query JobPostingInfoQuery("
        "$organizationHostedJobsPageName: String!, $jobPostingId: String!) {"
        "  jobPosting(organizationHostedJobsPageName: $organizationHostedJobsPageName,"
        "    jobPostingId: $jobPostingId) {"
        "    id title applicationForm {"
        "      sections { title fieldEntries { isRequired field } }"
        "    }"
        "  }"
        "}"
    )
    resp = requests.post(
        f"{ASHBY_GQL}?op=JobPostingInfoQuery",
        json={
            "operationName": "JobPostingInfoQuery",
            "variables": {
                "organizationHostedJobsPageName": slug,
                "jobPostingId": posting_id,
            },
            "query": query,
        },
        headers={"Content-Type": "application/json"},
        timeout=15,
    )
    if resp.status_code != 200:
        return None
    data = resp.json()
    if data.get("errors"):
        return None
    posting = (data.get("data") or {}).get("jobPosting")
    if not posting:
        return None
    return posting.get("applicationForm")


def apply_ashby(job: dict, resume_path: str, dry_run: bool = False) -> tuple[bool, str]:
    slug, posting_id = _extract_ashby_slug_and_id(job)
    if not posting_id:
        return False, "Could not extract Ashby posting ID from URL"

    form_def = get_ashby_form(slug, posting_id)
    if not form_def:
        return False, "Failed to fetch Ashby application form — posting may be closed"

    if dry_run:
        return True, f"[DRY RUN] Would submit to Ashby posting {posting_id}"

    try:
        from browser_apply import browser_apply
        result = browser_apply(
            job.get("url", ""), resume_path,
            cover_letter_path="", platform="ashby",
        )
        return result["ok"], result["message"]
    except ImportError:
        return False, (
            "Ashby requires browser automation (Playwright). "
            "Run: pip install playwright && python -m playwright install chromium"
        )


# ═══════════════════════════════════════════════════════════════════════════
#  LEVER APPLIER — REST API
# ═══════════════════════════════════════════════════════════════════════════

def _extract_lever_slug_and_id(job: dict) -> tuple[str, str]:
    url = job.get("url", "")
    match = re.search(r"lever\.co/([^/]+)/([a-f0-9\-]+)", url)
    if match:
        return match.group(1), match.group(2)
    return job.get("company", ""), job.get("source_job_id", "")


def apply_lever(job: dict, resume_path: str, dry_run: bool = False) -> tuple[bool, str]:
    slug, posting_id = _extract_lever_slug_and_id(job)
    if not slug or not posting_id:
        return False, "Could not extract Lever slug/posting ID from URL"

    if dry_run:
        return True, f"[DRY RUN] Would submit to Lever {slug}/{posting_id}"

    with open(resume_path, "rb") as f:
        files = {"resume": (os.path.basename(resume_path), f, "application/pdf")}
        data = {
            "name": CANDIDATE["first_name"] + " " + CANDIDATE["last_name"],
            "email": CANDIDATE["email"],
            "phone": CANDIDATE["phone"],
            "org": "University of Florida",
            "urls[LinkedIn]": CANDIDATE["linkedin"],
            "urls[GitHub]": CANDIDATE["github"],
            "comments": "",
        }
        resp = requests.post(
            f"https://api.lever.co/v0/postings/{slug}/{posting_id}/apply",
            data=data,
            files=files,
            headers=HEADERS,
            timeout=30,
        )

    if resp.status_code in (200, 201):
        result = resp.json()
        if result.get("ok"):
            return True, "Submitted successfully"
        return False, f"Lever rejected: {result}"
    return False, f"HTTP {resp.status_code}: {resp.text[:200]}"


# ═══════════════════════════════════════════════════════════════════════════
#  GREENHOUSE APPLIER — WEB FORM SUBMISSION
# ═══════════════════════════════════════════════════════════════════════════

def _extract_greenhouse_board_and_token(job: dict) -> tuple[str, str]:
    url = job.get("url", "")
    match = re.search(r"greenhouse\.io/([^/]+)/jobs/(\d+)", url)
    if match:
        return match.group(1), match.group(2)
    match = re.search(r"boards\.greenhouse\.io/([^/]+)/jobs/(\d+)", url)
    if match:
        return match.group(1), match.group(2)
    return "", job.get("source_job_id", "")


def apply_greenhouse(job: dict, resume_path: str, imap: imaplib.IMAP4_SSL | None = None,
                     dry_run: bool = False) -> tuple[bool, str]:
    board, job_token = _extract_greenhouse_board_and_token(job)
    if not board or not job_token:
        return False, "Could not extract Greenhouse board/token from URL"

    form_url = f"https://boards.greenhouse.io/embed/job_app?for={board}&token={job_token}"
    session = requests.Session()
    session.headers.update(HEADERS)

    resp = session.get(form_url, timeout=15)
    if resp.status_code != 200:
        return False, f"Failed to load form: HTTP {resp.status_code}"

    soup = BeautifulSoup(resp.text, "html.parser")

    authenticity_token = ""
    token_input = soup.find("input", {"name": "authenticity_token"})
    if token_input:
        authenticity_token = token_input.get("value", "")

    form_data = {
        "authenticity_token": authenticity_token,
        "job_application[first_name]": CANDIDATE["first_name"],
        "job_application[last_name]": CANDIDATE["last_name"],
        "job_application[email]": CANDIDATE["email"],
        "job_application[phone]": CANDIDATE["phone"],
        "job_application[location]": CANDIDATE["location"],
    }

    custom_fields = _parse_greenhouse_custom_fields(soup)
    form_data.update(custom_fields)

    if dry_run:
        return True, f"[DRY RUN] Would submit to Greenhouse {board}/jobs/{job_token} ({len(custom_fields)} custom fields)"

    with open(resume_path, "rb") as f:
        files = {"job_application[resume]": (os.path.basename(resume_path), f, "application/pdf")}
        submit_url = f"https://boards.greenhouse.io/embed/job_app?for={board}&token={job_token}"
        resp = session.post(submit_url, data=form_data, files=files, timeout=30)

    if resp.status_code in (200, 201, 302):
        if "verify" in resp.text.lower() or "confirmation" in resp.text.lower():
            return _handle_greenhouse_verification(session, resp, imap, board, job_token)
        return True, "Submitted successfully"

    return False, f"HTTP {resp.status_code}: {resp.text[:200]}"


def _parse_greenhouse_custom_fields(soup: BeautifulSoup) -> dict:
    fields = {}
    for field_div in soup.find_all("div", class_="field"):
        label_el = field_div.find("label")
        if not label_el:
            continue
        label_text = label_el.get_text(strip=True).lower()
        input_el = field_div.find("input") or field_div.find("select") or field_div.find("textarea")
        if not input_el:
            continue

        name = input_el.get("name", "")
        if not name or name in ("authenticity_token",):
            continue

        value = _answer_greenhouse_field(label_text, input_el)
        if value is not None:
            fields[name] = value

    return fields


def _answer_greenhouse_field(label: str, input_el) -> str | None:
    label = label.lower().strip()
    tag = input_el.name

    if any(k in label for k in ("linkedin", "linked in")):
        return CANDIDATE["linkedin"]
    if "github" in label:
        return CANDIDATE["github"]
    if "website" in label or "portfolio" in label:
        return CANDIDATE["website"] or CANDIDATE["github"]
    if "phone" in label:
        return CANDIDATE["phone"]

    if any(k in label for k in ("sponsor", "visa", "authorization", "authorized")):
        if tag == "select":
            options = input_el.find_all("option")
            for opt in options:
                val = opt.get_text(strip=True).lower()
                if "yes" in val or "now" in val or "future" in val:
                    return opt.get("value", opt.get_text(strip=True))
        return "Yes"

    if any(k in label for k in ("relocat",)):
        return "Yes"

    if any(k in label for k in ("start date", "earliest", "available")):
        return "End of 2026"

    if any(k in label for k in ("salary", "compensation", "pay")):
        return ""

    if any(k in label for k in ("hear about", "how did you", "referral", "source")):
        return "Company careers page"

    if any(k in label for k in ("gender", "race", "ethnicity", "veteran", "disability")):
        if tag == "select":
            options = input_el.find_all("option")
            for opt in options:
                val = opt.get_text(strip=True).lower()
                if "decline" in val or "prefer not" in val or "not" in val:
                    return opt.get("value", opt.get_text(strip=True))
        return "Decline to self-identify"

    if any(k in label for k in ("cover letter",)):
        return ""

    if tag == "select":
        options = input_el.find_all("option")
        non_empty = [o for o in options if o.get("value")]
        if non_empty:
            return non_empty[0].get("value", "")

    required = input_el.get("required") or input_el.get("aria-required")
    if required:
        return _answer_custom_question(label, input_el.get("name", ""))

    return None


def _handle_greenhouse_verification(session: requests.Session, resp: requests.Response,
                                    imap: imaplib.IMAP4_SSL | None,
                                    board: str, job_token: str) -> tuple[bool, str]:
    if not imap:
        return False, "Verification code required but Gmail IMAP not connected"

    print("    Waiting for verification code via email...")
    code = fetch_verification_code(imap, sender_pattern="greenhouse")
    if not code:
        return False, "Timed out waiting for verification code"

    print(f"    Got verification code: {code}")

    soup = BeautifulSoup(resp.text, "html.parser")
    verify_form = soup.find("form")
    if not verify_form:
        return False, "Could not find verification form in response"

    verify_data = {}
    for inp in verify_form.find_all("input"):
        name = inp.get("name", "")
        if name:
            verify_data[name] = inp.get("value", "")

    code_field = None
    for inp in verify_form.find_all("input"):
        input_type = inp.get("type", "").lower()
        if input_type in ("text", "number", "tel"):
            code_field = inp.get("name", "")
            break
    if not code_field:
        code_field = "verification_code"

    verify_data[code_field] = code

    action = verify_form.get("action", "")
    if not action.startswith("http"):
        action = f"https://boards.greenhouse.io{action}"

    resp2 = session.post(action, data=verify_data, timeout=15)
    if resp2.status_code in (200, 201, 302):
        return True, f"Submitted with verification code {code}"
    return False, f"Verification submission failed: HTTP {resp2.status_code}"


# ═══════════════════════════════════════════════════════════════════════════
#  SMARTRECRUITERS APPLIER — HOSTED FORM SUBMISSION
# ═══════════════════════════════════════════════════════════════════════════

def _extract_smartrecruiters_apply_url(job: dict) -> str:
    url = job.get("url", "")
    match = re.search(r"smartrecruiters\.com/(.+?)/([\w-]+)", url)
    if match:
        return f"https://jobs.smartrecruiters.com/{match.group(1)}/{match.group(2)}/apply"
    job_id = job.get("source_job_id", "")
    company = job.get("company", "")
    if job_id and company:
        return f"https://jobs.smartrecruiters.com/{company}/{job_id}/apply"
    return ""


def apply_smartrecruiters(job: dict, resume_path: str, dry_run: bool = False) -> tuple[bool, str]:
    apply_url = _extract_smartrecruiters_apply_url(job)
    if not apply_url:
        return False, "Could not construct SmartRecruiters apply URL"

    if dry_run:
        return True, f"[DRY RUN] Would submit to SmartRecruiters: {apply_url}"

    session = requests.Session()
    session.headers.update(HEADERS)
    resp = session.get(apply_url, timeout=15, allow_redirects=True)
    if resp.status_code != 200:
        return False, f"Failed to load apply page: HTTP {resp.status_code}"

    soup = BeautifulSoup(resp.text, "html.parser")
    form = soup.find("form")
    if not form:
        return False, "No application form found on page"

    form_data = {}
    for inp in form.find_all(["input", "select", "textarea"]):
        name = inp.get("name", "")
        if not name:
            continue
        value = inp.get("value", "")
        form_data[name] = value

    field_mapping = {
        "firstName": CANDIDATE["first_name"],
        "lastName": CANDIDATE["last_name"],
        "email": CANDIDATE["email"],
        "phone": CANDIDATE["phone"],
        "location": CANDIDATE["location"],
        "linkedinUrl": CANDIDATE["linkedin"],
        "linkedin": CANDIDATE["linkedin"],
    }
    for key, val in field_mapping.items():
        for form_key in form_data:
            if key.lower() in form_key.lower():
                form_data[form_key] = val

    custom_fields = _parse_greenhouse_custom_fields(soup)
    form_data.update(custom_fields)

    action = form.get("action", apply_url)
    if not action.startswith("http"):
        action = f"https://jobs.smartrecruiters.com{action}"

    with open(resume_path, "rb") as f:
        files = {"resume": (os.path.basename(resume_path), f, "application/pdf")}
        resp = session.post(action, data=form_data, files=files, timeout=30)

    if resp.status_code in (200, 201, 302):
        return True, "Submitted successfully"
    return False, f"HTTP {resp.status_code}: {resp.text[:200]}"


# ═══════════════════════════════════════════════════════════════════════════
#  WORKABLE APPLIER — HOSTED FORM SUBMISSION
# ═══════════════════════════════════════════════════════════════════════════

def _extract_workable_apply_url(job: dict) -> str:
    url = job.get("url", "")
    if "/apply" in url:
        return url
    shortcode = job.get("source_job_id", "")
    if shortcode:
        return f"https://apply.workable.com/j/{shortcode}/apply/"
    if url and "workable.com" in url:
        return url.rstrip("/") + "/apply/"
    return ""


def apply_workable(job: dict, resume_path: str, dry_run: bool = False) -> tuple[bool, str]:
    apply_url = _extract_workable_apply_url(job)
    if not apply_url:
        return False, "Could not construct Workable apply URL"

    if dry_run:
        return True, f"[DRY RUN] Would submit to Workable: {apply_url}"

    session = requests.Session()
    session.headers.update(HEADERS)
    resp = session.get(apply_url, timeout=15, allow_redirects=True)
    if resp.status_code != 200:
        return False, f"Failed to load apply page: HTTP {resp.status_code}"

    soup = BeautifulSoup(resp.text, "html.parser")
    form = soup.find("form")
    if not form:
        return False, "No application form found on page"

    form_data = {}
    for inp in form.find_all(["input", "select", "textarea"]):
        name = inp.get("name", "")
        if not name:
            continue
        form_data[name] = inp.get("value", "")

    candidate_fields = {
        "firstname": CANDIDATE["first_name"],
        "first_name": CANDIDATE["first_name"],
        "lastname": CANDIDATE["last_name"],
        "last_name": CANDIDATE["last_name"],
        "email": CANDIDATE["email"],
        "phone": CANDIDATE["phone"],
        "address": CANDIDATE["location"],
        "linkedin": CANDIDATE["linkedin"],
    }
    for form_key in list(form_data.keys()):
        for cand_key, cand_val in candidate_fields.items():
            if cand_key in form_key.lower():
                form_data[form_key] = cand_val
                break

    custom_fields = _parse_greenhouse_custom_fields(soup)
    form_data.update(custom_fields)

    action = form.get("action", apply_url)
    if not action.startswith("http"):
        action = f"https://apply.workable.com{action}"

    with open(resume_path, "rb") as f:
        files = {"resume": (os.path.basename(resume_path), f, "application/pdf")}
        resp = session.post(action, data=form_data, files=files, timeout=30)

    if resp.status_code in (200, 201, 302):
        return True, "Submitted successfully"
    return False, f"HTTP {resp.status_code}: {resp.text[:200]}"


# ═══════════════════════════════════════════════════════════════════════════
#  BAMBOOHR APPLIER — HOSTED FORM SUBMISSION
# ═══════════════════════════════════════════════════════════════════════════

def _extract_bamboohr_info(job: dict) -> tuple[str, str]:
    url = job.get("url", "")
    match = re.search(r"(\w+)\.bamboohr\.com/careers/(\d+)", url)
    if match:
        return match.group(1), match.group(2)
    return job.get("company", ""), job.get("source_job_id", "")


def apply_bamboohr(job: dict, resume_path: str, dry_run: bool = False) -> tuple[bool, str]:
    slug, job_id = _extract_bamboohr_info(job)
    if not slug or not job_id:
        return False, "Could not extract BambooHR slug/job ID"

    apply_url = f"https://{slug}.bamboohr.com/careers/{job_id}/detail/apply"

    if dry_run:
        return True, f"[DRY RUN] Would submit to BambooHR: {apply_url}"

    session = requests.Session()
    session.headers.update(HEADERS)
    resp = session.get(apply_url, timeout=15, allow_redirects=True)
    if resp.status_code != 200:
        return False, f"Failed to load apply page: HTTP {resp.status_code}"

    soup = BeautifulSoup(resp.text, "html.parser")
    form = soup.find("form")
    if not form:
        return False, "No application form found on page"

    form_data = {}
    for inp in form.find_all(["input", "select", "textarea"]):
        name = inp.get("name", "")
        if not name:
            continue
        form_data[name] = inp.get("value", "")

    candidate_fields = {
        "firstName": CANDIDATE["first_name"],
        "first_name": CANDIDATE["first_name"],
        "lastName": CANDIDATE["last_name"],
        "last_name": CANDIDATE["last_name"],
        "email": CANDIDATE["email"],
        "phone": CANDIDATE["phone"],
        "city": CANDIDATE["location"].split(",")[0].strip(),
        "linkedin": CANDIDATE["linkedin"],
    }
    for form_key in list(form_data.keys()):
        for cand_key, cand_val in candidate_fields.items():
            if cand_key.lower() in form_key.lower():
                form_data[form_key] = cand_val
                break

    custom_fields = _parse_greenhouse_custom_fields(soup)
    form_data.update(custom_fields)

    action = form.get("action", apply_url)
    if not action.startswith("http"):
        action = f"https://{slug}.bamboohr.com{action}"

    with open(resume_path, "rb") as f:
        files = {"resume": (os.path.basename(resume_path), f, "application/pdf")}
        resp = session.post(action, data=form_data, files=files, timeout=30)

    if resp.status_code in (200, 201, 302):
        return True, "Submitted successfully"
    return False, f"HTTP {resp.status_code}: {resp.text[:200]}"


# ═══════════════════════════════════════════════════════════════════════════
#  WORKDAY APPLIER — SESSION-BASED FORM SUBMISSION
# ═══════════════════════════════════════════════════════════════════════════

def _extract_workday_info(job: dict) -> tuple[str, str, str, str]:
    url = job.get("url", "")
    match = re.search(
        r"(\w+)\.(wd\d+)\.myworkdayjobs\.com/(?:en-US/)?([^/]+)/job/[^/]+/([^?]+)", url
    )
    if match:
        return match.group(1), match.group(2), match.group(3), match.group(4)
    return "", "", "", ""


def apply_workday(job: dict, resume_path: str, dry_run: bool = False) -> tuple[bool, str]:
    slug, wd, site, job_path = _extract_workday_info(job)
    if not slug or not job_path:
        return False, "Could not extract Workday job info from URL"

    apply_url = job.get("url", "")
    if dry_run:
        return True, f"[DRY RUN] Would submit to Workday: {apply_url}"

    session = requests.Session()
    session.headers.update(HEADERS)

    resp = session.get(apply_url, timeout=15, allow_redirects=True)
    if resp.status_code != 200:
        return False, f"Failed to load job page: HTTP {resp.status_code}"

    apply_page_url = f"https://{slug}.{wd}.myworkdayjobs.com/en-US/{site}/job/{job_path}/apply"
    resp = session.get(apply_page_url, timeout=15, allow_redirects=True)
    if resp.status_code != 200:
        return False, f"Failed to load apply page: HTTP {resp.status_code}"

    soup = BeautifulSoup(resp.text, "html.parser")
    form = soup.find("form")
    if not form:
        return False, "No application form found (Workday may require browser-based submission)"

    form_data = {}
    for inp in form.find_all(["input", "select", "textarea"]):
        name = inp.get("name", "")
        if not name:
            continue
        form_data[name] = inp.get("value", "")

    candidate_fields = {
        "firstName": CANDIDATE["first_name"],
        "lastName": CANDIDATE["last_name"],
        "email": CANDIDATE["email"],
        "phone": CANDIDATE["phone"],
        "linkedin": CANDIDATE["linkedin"],
    }
    for form_key in list(form_data.keys()):
        for cand_key, cand_val in candidate_fields.items():
            if cand_key.lower() in form_key.lower():
                form_data[form_key] = cand_val
                break

    action = form.get("action", apply_page_url)
    if not action.startswith("http"):
        action = f"https://{slug}.{wd}.myworkdayjobs.com{action}"

    with open(resume_path, "rb") as f:
        files = {"resume": (os.path.basename(resume_path), f, "application/pdf")}
        resp = session.post(action, data=form_data, files=files, timeout=30)

    if resp.status_code in (200, 201, 302):
        return True, "Submitted successfully"
    return False, f"HTTP {resp.status_code}: {resp.text[:200]}"


# ═══════════════════════════════════════════════════════════════════════════
#  CUSTOM QUESTION ANSWERING
# ═══════════════════════════════════════════════════════════════════════════

_CUSTOM_ANSWERS = {
    "years of experience": "3",
    "degree": "Master's",
    "education": "Master of Science in Computer Science, University of Florida",
    "gpa": "3.81",
    "citizenship": "No",
    "work authorization": "Yes, with sponsorship",
    "visa": "Yes, will need sponsorship",
    "legally authorized": "Yes",
    "sponsorship": "Yes",
    "relocate": "Yes",
    "remote": "Yes",
    "onsite": "Yes",
    "hybrid": "Yes",
    "clearance": "No",
    "age": "Yes",
    "18 years": "Yes",
}


def _answer_custom_question(label: str, field_name: str = "") -> str:
    label_lower = label.lower().strip()
    for keyword, answer in _CUSTOM_ANSWERS.items():
        if keyword in label_lower:
            return answer
    return ""


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN DISPATCHER
# ═══════════════════════════════════════════════════════════════════════════

APPLIERS = {
    "ashby": apply_ashby,
    "lever": apply_lever,
    "greenhouse": apply_greenhouse,
    "smartrecruiters": apply_smartrecruiters,
    "workable": apply_workable,
    "bamboohr": apply_bamboohr,
    "workday": apply_workday,
}

PROGRESS_FILE = os.path.join(OUTPUT_DIR, "auto_apply_progress.json")
DEFAULT_COVER_LETTER = r"C:\Users\tirun\OneDrive\Desktop\Job Applications\April\Cover Letters\CoverLetter.docx"


def _write_progress(progress: dict):
    try:
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(progress, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def load_ranked_jobs() -> list:
    if os.path.exists(RANKED_JOBS):
        with open(RANKED_JOBS, encoding="utf-8") as f:
            return json.load(f)
    return []


def auto_apply(source_filter: str | None = None, dry_run: bool = False):
    jobs = load_ranked_jobs()
    if not jobs:
        print("[auto_apply] No ranked jobs found. Run the pipeline first.")
        return

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    eligible = [
        j for j in jobs
        if j.get("source", "").lower() in APPLIERS
        and (not source_filter or j.get("source", "").lower() == source_filter.lower())
    ]

    imap = None
    has_greenhouse = any(j.get("source") == "greenhouse" for j in eligible)
    if has_greenhouse and GMAIL_APP_PASSWORD and not dry_run:
        imap = connect_gmail()

    applied = 0
    skipped = 0
    failed = 0
    results = []

    progress = {
        "running": True,
        "started_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "dry_run": dry_run,
        "current": 0,
        "total": len(eligible),
        "current_job": None,
        "applied": 0,
        "skipped": 0,
        "failed": 0,
        "results": [],
    }
    _write_progress(progress)

    for i, job in enumerate(eligible, 1):
        source = job.get("source", "").lower()
        title = job.get("title", "Unknown")
        company = job.get("company", "Unknown")
        url = job.get("url", "")

        progress["current"] = i
        progress["current_job"] = {"title": title, "company": company, "source": source}
        _write_progress(progress)

        if is_already_applied(conn, url):
            skipped += 1
            progress["skipped"] = skipped
            results.append({"title": title, "company": company, "source": source, "status": "skipped", "error": ""})
            progress["results"] = results
            _write_progress(progress)
            print(f"  [{i}] SKIP (already applied) {title} @ {company}")
            continue

        resume_path = find_resume_pdf(job)
        if not resume_path:
            print(f"  [{i}] SKIP (no resume PDF) {title} @ {company}")
            skipped += 1
            progress["skipped"] = skipped
            results.append({"title": title, "company": company, "source": source, "status": "skipped", "error": "No resume PDF"})
            progress["results"] = results
            _write_progress(progress)
            continue

        print(f"\n  [{i}] APPLYING: {title} @ {company} [{source}]")
        print(f"       Resume: {os.path.basename(resume_path)}")

        try:
            if source == "greenhouse":
                ok, msg = apply_greenhouse(job, resume_path, imap=imap, dry_run=dry_run)
            else:
                ok, msg = APPLIERS[source](job, resume_path, dry_run=dry_run)

            if ok:
                applied += 1
                status = "dry_run" if dry_run else "submitted"
                record_application(conn, job, source, status=status)
                results.append({"title": title, "company": company, "source": source, "status": status, "error": ""})
                print(f"       OK {msg}")
            else:
                failed += 1
                record_application(conn, job, source, status="failed", error=msg)
                results.append({"title": title, "company": company, "source": source, "status": "failed", "error": msg})
                print(f"       FAIL {msg}")

        except Exception as e:
            failed += 1
            record_application(conn, job, source, status="error", error=str(e))
            results.append({"title": title, "company": company, "source": source, "status": "error", "error": str(e)})
            print(f"       FAIL Exception: {e}")

        progress["applied"] = applied
        progress["failed"] = failed
        progress["results"] = results
        _write_progress(progress)

        if not dry_run:
            time.sleep(2)

    if imap:
        try:
            imap.logout()
        except Exception:
            pass

    conn.close()

    progress["running"] = False
    progress["finished_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    progress["current_job"] = None
    _write_progress(progress)

    print(f"\n{'='*60}")
    print(f"  Auto-Apply Summary")
    print(f"  Applied: {applied}  |  Skipped: {skipped}  |  Failed: {failed}")
    print(f"{'='*60}\n")


# ═══════════════════════════════════════════════════════════════════════════
#  SINGLE-JOB APPLY (used by the UI page)
# ═══════════════════════════════════════════════════════════════════════════

_PLATFORM_PATTERNS = [
    ("greenhouse", r"greenhouse\.io"),
    ("lever", r"lever\.co"),
    ("ashby", r"ashbyhq\.com"),
    ("workday", r"myworkdayjobs\.com"),
    ("smartrecruiters", r"smartrecruiters\.com"),
    ("workable", r"workable\.com"),
    ("bamboohr", r"bamboohr\.com"),
]


def detect_platform(url: str) -> str:
    for name, pattern in _PLATFORM_PATTERNS:
        if re.search(pattern, url, re.IGNORECASE):
            return name
    return ""


_BROWSER_PLATFORMS = {"ashby", "workable"}


def single_apply(url: str, resume_path: str, cover_letter_path: str = "",
                 dry_run: bool = False) -> dict:
    """Apply to a single job by URL. Returns {ok, platform, message}."""
    platform = detect_platform(url)
    if not platform:
        return {"ok": False, "platform": "", "message": f"Could not detect platform from URL: {url}"}

    if not os.path.exists(resume_path):
        return {"ok": False, "platform": platform, "message": f"Resume not found: {resume_path}"}

    job = {
        "url": url,
        "source": platform,
        "source_job_id": url.rstrip("/").split("/")[-1],
        "title": "",
        "company": "",
    }

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    if is_already_applied(conn, url):
        conn.close()
        return {"ok": False, "platform": platform, "message": "Already applied to this job"}

    if platform in _BROWSER_PLATFORMS and not dry_run:
        try:
            from browser_apply import browser_apply
            result = browser_apply(
                url, resume_path,
                cover_letter_path=cover_letter_path,
                platform=platform,
            )
            status = "submitted" if result["ok"] else "failed"
            record_application(conn, job, platform, status=status,
                               error="" if result["ok"] else result["message"])
            conn.close()
            return result
        except ImportError:
            conn.close()
            return {
                "ok": False, "platform": platform,
                "message": "Playwright not installed. Run: pip install playwright && python -m playwright install chromium",
            }

    imap = None
    if platform == "greenhouse" and GMAIL_APP_PASSWORD and not dry_run:
        imap = connect_gmail()

    try:
        if platform == "greenhouse":
            ok, msg = apply_greenhouse(job, resume_path, imap=imap, dry_run=dry_run)
        else:
            ok, msg = APPLIERS[platform](job, resume_path, dry_run=dry_run)

        status = ("dry_run" if dry_run else "submitted") if ok else "failed"
        record_application(conn, job, platform, status=status, error="" if ok else msg)
        conn.close()

        if imap:
            try:
                imap.logout()
            except Exception:
                pass

        return {"ok": ok, "platform": platform, "message": msg}

    except Exception as e:
        record_application(conn, job, platform, status="error", error=str(e))
        conn.close()
        return {"ok": False, "platform": platform, "message": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Auto-apply to Greenhouse, Ashby, and Lever jobs")
    parser.add_argument("--dry-run", action="store_true", help="Preview applications without submitting")
    parser.add_argument("--source",
                        choices=["greenhouse", "ashby", "lever", "smartrecruiters", "workable", "bamboohr", "workday"],
                        help="Only apply to jobs from this source")
    args = parser.parse_args()
    auto_apply(source_filter=args.source, dry_run=args.dry_run)
