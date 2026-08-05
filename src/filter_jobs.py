"""
filter_jobs.py
Filters raw_jobs.json by: title relevance, entry-level signals, US/remote location.
Outputs filtered_jobs.json.
"""
import json
import os
import re
import sqlite3
import yaml
from datetime import datetime, timedelta

# ── Path resolution ─────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
DB_PATH = os.path.join(BASE_DIR, "db", "jobs.db")

RAW_INPUT = os.path.join(OUTPUT_DIR, "raw_jobs.json")
FILTERED_OUTPUT = os.path.join(OUTPUT_DIR, "filtered_jobs.json")

# Titles that match target roles
TITLE_KEYWORDS = [
    # Core SWE
    "software engineer", "software developer", "swe",
    # AI / ML
    "ai engineer", "ml engineer", "machine learning engineer",
    "artificial intelligence engineer",
    "deep learning", "computer vision",
    "ai researcher", "ml researcher",
    # Backend / Full-stack
    "backend engineer", "backend developer",
    "full stack", "fullstack", "full-stack",
    # Platform / Data
    "ai platform", "platform engineer",
    "data engineer", "data scientist", "data analyst",
    # LLM / GenAI
    "llm engineer", "generative ai", "gen ai",
    # Language / framework-specific
    "java engineer", "java developer",
    "python engineer", "python developer",
    "react developer",
    "android developer",
    # Other target roles
    "application developer", "systems engineer",
    "ui/ux developer", "ui developer", "ux developer",
    "database administrator",
    # Entry-level signals
    "new grad", "early career", "entry level", "entry-level",
]

# Only checked against the TITLE — these disqualify the role itself
TITLE_SENIORITY_EXCLUDE = [
    "senior", " sr.", " sr ", "staff engineer", "principal",
    " lead ", "tech lead", "director", " manager", "vp ",
    "vice president", "head of", "architect",
    "intern", "internship", "co-op", "coop",
]

# Checked against title + FULL description — explicit experience requirements
DESCRIPTION_EXPERIENCE_EXCLUDE = [
    # 3+ years and above (roles requiring up to 2 years are allowed)
    "5+ years", "6+ years", "7+ years", "8+ years", "10+ years",
    "3+ years", "4+ years", "five years", "seven years",
    "minimum 3 years", "minimum 4 years", "minimum 5 years",
    "at least 3 years", "at least 4 years", "at least 5 years",
    "3 years of experience", "4 years of experience", "5 years of experience",
    "3 years experience", "4 years experience", "5 years experience",
    "3+ years experience", "4+ years experience", "5+ years experience",
]

# ── H1B / Visa sponsorship ─────────────────────────────────────────────────

# Companies in the USCIS LCA public dataset known to regularly sponsor H1B.
# This is a representative subset — add more as needed.
_KNOWN_H1B_SPONSORS: set[str] = {
    # Big tech
    "google", "amazon", "microsoft", "meta", "apple", "netflix",
    "salesforce", "oracle", "ibm", "intel", "qualcomm", "nvidia",
    # Cloud / infra
    "aws", "azure", "gcp", "cloudflare", "datadog", "hashicorp",
    "mongodb", "elastic", "snowflake", "databricks", "cockroachdb",
    # AI / ML
    "openai", "anthropic", "cohere", "scale ai", "anyscale", "together ai",
    "hugging face", "wandb", "perplexity",
    # Fintech / SaaS
    "stripe", "brex", "ramp", "rippling", "shopify", "atlassian",
    "twilio", "zendesk", "hubspot", "intercom", "amplitude",
    # Other notable
    "reddit", "discord", "notion", "figma", "canva", "airtable",
    "retool", "vercel", "supabase", "github", "gitlab",
    "uber", "lyft", "airbnb", "pinterest", "dropbox", "zoom",
    "palantir", "waymo", "tesla", "spacex", "rivian",
    # IT staffing / consulting that frequently sponsors H1B
    "infosys", "tata consultancy", "tcs", "wipro", "cognizant",
    "hcl", "capgemini", "accenture", "deloitte", "pwc",
}

# Positive signals in job description that explicitly confirm sponsorship
_H1B_POSITIVE_SIGNALS = [
    "h1b", "h-1b", "visa sponsorship", "sponsor visa", "sponsorship available",
    "sponsorship provided", "sponsorship considered",
    "will sponsor", "does sponsor", "we sponsor",
    "sponsorship for this role", "immigration assistance",
    "opt/cpt", "opt cpt", "f1 visa", "work authorization provided",
    # OPT / contract-friendly signals
    "opt eligible", "opt friendly", "opt accepted",
    "contract to hire", "c2h", "corp to corp", "c2c",
    "w2 contract",
]


def is_h1b_friendly(company: str, description: str) -> bool:
    """Return True if the job is likely H1B-friendly.

    Passes if EITHER:
    - The company name matches a known H1B sponsor, OR
    - The description contains an explicit positive sponsorship signal.

    When neither is present the job is still included (benefit of the doubt),
    but it will have been through the hard negative-signal check first.
    """
    company_lower = company.lower()
    if any(sponsor in company_lower for sponsor in _KNOWN_H1B_SPONSORS):
        return True
    desc_lower = description.lower()
    if any(sig in desc_lower for sig in _H1B_POSITIVE_SIGNALS):
        return True
    return False


# Phrases that indicate no visa sponsorship — hard exclude
_NO_SPONSORSHIP_SIGNALS = [
    "ITAR requirements",  
    "no sponsorship",
    "sponsorship not available",
    "will not sponsor",
    "cannot sponsor",
    "does not provide sponsorship",
    "unable to sponsor",
    "not able to sponsor",
    "without sponsorship",
    "must be authorized to work",
    "must be legally authorized",
    "must have work authorization",
    "must already be authorized",
    "u.s. citizens only",
    "us citizens only",
    "citizens only",
    "green card only",
    "green card holders only",
    "permanent resident only",
    "permanent residents only",
    "citizenship required",
    "security clearance required",
    "clearance required",
    "active clearance",
    "must be a u.s. citizen",
    "must be a us citizen",
]


def requires_no_sponsorship(title: str, description: str) -> bool:
    """Return True (i.e. disqualify) if the job explicitly excludes visa sponsorship."""
    text = (title + " " + description).lower()
    return any(sig in text for sig in _NO_SPONSORSHIP_SIGNALS)

# US state abbreviations — catches "Columbus, OH", "Chicago, IL" etc.
_US_STATE_ABBR = re.compile(
    r",\s*("
    r"AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|"
    r"MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|"
    r"WA|WV|WI|WY|DC"
    r")(\s|$)"
)



def load_config():
    with open(os.path.join(BASE_DIR, "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_applied_urls() -> set:
    """Return the set of URLs already marked as applied in the DB."""
    if not os.path.exists(DB_PATH):
        return set()
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("SELECT url FROM applied_jobs WHERE url IS NOT NULL").fetchall()
        conn.close()
        return {row[0] for row in rows}
    except Exception:
        return set()


def is_relevant_title(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in TITLE_KEYWORDS)


def is_entry_level(title: str, description: str) -> bool:
    title_lower = title.lower()
    # Disqualify based on title only — role-level words in description are context, not requirements
    if any(sig in title_lower for sig in TITLE_SENIORITY_EXCLUDE):
        return False
    # Disqualify based on explicit experience requirements — check FULL description
    desc_lower = description.lower()
    if any(sig in desc_lower for sig in DESCRIPTION_EXPERIENCE_EXCLUDE):
        return False
    return True


# Keywords indicating a location is remote/anywhere
_REMOTE_KEYWORDS = ["remote", "anywhere", "worldwide", "distributed", "nationwide"]

# Country/region keywords for common locations
_LOCATION_KEYWORDS: dict[str, list[str]] = {
    "united states": ["united states", " us ", "u.s.", "usa", "new york", "san francisco",
                      "seattle", "chicago", "austin", "boston", "los angeles", "denver",
                      "atlanta", "miami", "washington", "county", "metropolitan"],
    "india": ["india", "bangalore", "bengaluru", "mumbai", "delhi", "hyderabad",
              "chennai", "pune", "noida", "gurugram", "gurgaon", "kolkata"],
    "united kingdom": ["united kingdom", "uk", "england", "london", "manchester",
                       "birmingham", "bristol", "edinburgh"],
    "canada": ["canada", "toronto", "vancouver", "montreal", "ontario", "british columbia"],
    "australia": ["australia", "sydney", "melbourne", "brisbane", "perth"],
    "germany": ["germany", "berlin", "munich", "hamburg", "frankfurt"],
}


def _location_matches(job_loc: str, configured: str) -> bool:
    """Return True if job_loc matches the configured location or is remote."""
    loc = job_loc.lower().strip()
    # Always accept remote jobs regardless of configured location
    if any(r in loc for r in _REMOTE_KEYWORDS):
        return True
    conf = configured.lower().strip()
    # Direct substring match
    if conf in loc or loc in conf:
        return True
    # Check known keyword list for configured location
    keywords = _LOCATION_KEYWORDS.get(conf, [])
    return any(kw in loc for kw in keywords)


def is_us_or_remote(location: str, source: str = "", configured_location: str = "United States") -> bool:
    if not location:
        return True
    # Adzuna only returns jobs for the country it was queried for — trust it unconditionally
    if source == "adzuna":
        return True
    # For US, also check state abbreviations
    if "united states" in configured_location.lower() or configured_location.lower() in ("us", "usa"):
        if _US_STATE_ABBR.search(location):
            return True
    return _location_matches(location, configured_location)


def is_recent(posted_at: str, hours: int) -> bool:
    """Return True if posted within `hours` hours, or if date is unparseable."""
    if not posted_at:
        return True  # be lenient when date is missing
    formats = [
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(posted_at[: len(fmt)], fmt)
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            return dt >= cutoff
        except (ValueError, TypeError):
            continue
    return True  # unknown format -> include


def filter_jobs():
    config = load_config()
    hours = config["filters"].get("posted_within_hours", 24)
    configured_location = config["filters"].get("location", "United States")
    blocked_companies = [c.lower() for c in config.get("blocked_companies", [])]

    with open(RAW_INPUT, encoding="utf-8") as f:
        jobs = json.load(f)

    applied_urls = load_applied_urls()
    if applied_urls:
        print(f"[filter] Excluding {len(applied_urls)} already-applied job(s).")

    filtered = []
    reasons = {"applied": 0, "title": 0, "seniority": 0, "location": 0, "sponsorship": 0, "blocked": 0, "passed": 0}

    for job in jobs:
        title = job.get("title", "")
        description = job.get("description", "")
        location = job.get("location", "")
        posted_at = job.get("posted_at", "")
        company_lower = job.get("company", "").lower()

        if job.get("url") in applied_urls:
            reasons["applied"] += 1
            continue

        if blocked_companies and any(b in company_lower for b in blocked_companies):
            reasons["blocked"] += 1
            continue

        if not is_relevant_title(title):
            reasons["title"] += 1
            continue

        if not is_entry_level(title, description):
            reasons["seniority"] += 1
            continue

        if not is_us_or_remote(location, source=job.get("source", ""), configured_location=configured_location):
            reasons["location"] += 1
            continue

        if requires_no_sponsorship(title, description):
            reasons["sponsorship"] += 1
            continue

        # Date filter: be lenient on Greenhouse (dates can be old posting refreshes)
        # Only apply strict date filter to LinkedIn/Glassdoor/Adzuna
        if job.get("source") in ("linkedin", "glassdoor", "adzuna", "jobright"):
            if not is_recent(posted_at, hours):
                continue

        # Tag H1B friendliness so the AI ranker can boost confirmed sponsors
        job["h1b_friendly"] = is_h1b_friendly(job.get("company", ""), description)

        reasons["passed"] += 1
        filtered.append(job)

    with open(FILTERED_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(filtered, f, indent=2, ensure_ascii=False)

    h1b_count = sum(1 for j in filtered if j.get("h1b_friendly"))
    print(
        f"[filter] {len(jobs)} raw -> {len(filtered)} passed "
        f"(dropped: applied={reasons['applied']}, title={reasons['title']}, "
        f"seniority={reasons['seniority']}, location={reasons['location']}, "
        f"sponsorship={reasons['sponsorship']}, blocked={reasons['blocked']}) "
        f"| h1b_friendly={h1b_count}/{len(filtered)} -> saved to {FILTERED_OUTPUT}"
    )
    return filtered


if __name__ == "__main__":
    filter_jobs()
