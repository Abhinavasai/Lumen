"""
fetch_jobs.py
Fetches jobs from 9 sources. Auto-apply platforms (Greenhouse, Lever, Ashby,
Workday, SmartRecruiters, Workable, BambooHR) run first, then passive sources
(LinkedIn, Adzuna). Outputs all results normalized to raw_jobs.json.
"""
import json
import os
import re
import time
import requests
import yaml
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# ── Path resolution ─────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)
load_dotenv(os.path.join(BASE_DIR, ".env"))

ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY")
APIFY_TOKEN = os.getenv("APIFY_TOKEN")
RAW_OUTPUT = os.path.join(OUTPUT_DIR, "raw_jobs.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def load_config():
    with open(os.path.join(BASE_DIR, "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def normalize_job(source, job_id, company, title, location, url, description, posted_at):
    return {
        "source": source,
        "source_job_id": str(job_id) if job_id else "",
        "company": (company or "").strip(),
        "title": (title or "").strip(),
        "location": (location or "").strip(),
        "url": (url or "").strip(),
        "description": (description or "").strip(),
        "posted_at": (posted_at or "").strip(),
    }


# ---------------------------------------------------------------------------
# Source 1a: LinkedIn -- Apify actor (primary)
# ---------------------------------------------------------------------------

def fetch_linkedin_apify(keywords: list, max_results: int, location: str = "United States") -> list:
    """
    Uses the Apify curious_coder/linkedin-jobs-scraper actor.
    Input: LinkedIn search URLs (one per keyword) + count.
    Actor ID: hKByXkMQaC5Qt9UMN
    """
    if not APIFY_TOKEN:
        print("  [Apify] APIFY_TOKEN not set, skipping.")
        return []

    try:
        from apify_client import ApifyClient
    except ImportError:
        print("  [Apify] apify-client not installed. Run: pip install apify-client")
        return []

    jobs = []
    seen_urls: set = set()
    client = ApifyClient(APIFY_TOKEN)

    per_kw = max(25, max_results // max(len(keywords), 1))

    for keyword in keywords:
        try:
            search_url = (
                "https://www.linkedin.com/jobs/search/?"
                f"keywords={requests.utils.quote(keyword)}"
                f"&location={requests.utils.quote(location)}"
                "&f_TPR=r86400"
            )
            run_input = {
                "urls": [search_url],
                "count": per_kw,
            }
            run = client.actor("hKByXkMQaC5Qt9UMN").call(run_input=run_input)
            dataset_id = run["defaultDatasetId"] if isinstance(run, dict) else run.default_dataset_id
            for item in client.dataset(dataset_id).iterate_items():
                url = (
                    item.get("link") or item.get("jobUrl")
                    or item.get("url") or item.get("applyUrl") or ""
                )
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                job_id = url.rstrip("/").split("-")[-1]
                if not job_id.isdigit():
                    job_id = ""
                description = (
                    item.get("description")
                    or item.get("descriptionHtml")
                    or (fetch_linkedin_description(job_id) if job_id else "")
                    or ""
                )
                jobs.append(normalize_job(
                    source="linkedin",
                    job_id=job_id or str(item.get("id", "")),
                    company=item.get("companyName") or item.get("company") or "",
                    title=item.get("title") or item.get("positionName") or "",
                    location=item.get("location") or "",
                    url=url,
                    description=description,
                    posted_at=(item.get("postedDate") or item.get("date") or item.get("postedAt") or "")[:10],
                ))
        except Exception as e:
            print(f"  [Apify] Error for '{keyword}': {e}")

    print(f"  [Apify] Total: {len(jobs)} jobs")
    return jobs


# Source 1b: LinkedIn -- direct guest API (fallback if Apify fails)
# ---------------------------------------------------------------------------

def fetch_linkedin_description(job_id: str) -> str:
    """Fetch full job description from LinkedIn guest job posting page."""
    try:
        url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")
        desc_div = soup.find("div", class_="description__text")
        if desc_div:
            return desc_div.get_text(separator=" ", strip=True)
        return ""
    except Exception:
        return ""


def fetch_linkedin_direct(keywords: list, max_results: int, location: str = "United States") -> list:
    """
    LinkedIn public guest job search â€" no API key, no scraper, no paid actor.
    Endpoint: linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search
    f_TPR=r86400  â†' posted in last 24 hours
    """
    jobs = []
    seen_ids: set[str] = set()
    per_kw = max(25, max_results // max(len(keywords), 1))

    for keyword in keywords:
        kw_count = 0
        start = 0
        while kw_count < per_kw:
            try:
                url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
                params = {
                    "keywords": keyword,
                    "location": location,
                    "start": start,
                    "f_TPR": "r86400",   # last 24 hours
                }
                resp = requests.get(url, params=params, headers=HEADERS, timeout=20)
                if resp.status_code != 200:
                    print(f"  [LinkedIn] HTTP {resp.status_code} for '{keyword}' start={start}")
                    break

                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.find_all("li")
                if not cards:
                    break

                new_this_page = 0
                for card in cards:
                    # data-entity-urn is on the inner div, not the <li>
                    card_div = card.find("div", attrs={"data-entity-urn": True})
                    if not card_div:
                        continue
                    job_id = card_div.get("data-entity-urn", "").split(":")[-1]
                    if not job_id or job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)

                    title_el = card.find(class_="base-search-card__title")
                    company_el = card.find(class_="base-search-card__subtitle")
                    location_el = card.find(class_="job-search-card__location")
                    link_el = card.find("a", class_="base-card__full-link")
                    time_el = card.find("time")

                    title = title_el.get_text(strip=True) if title_el else ""
                    company = company_el.get_text(strip=True) if company_el else ""
                    job_location = location_el.get_text(strip=True) if location_el else ""
                    job_url = link_el["href"].split("?")[0] if link_el else f"https://www.linkedin.com/jobs/view/{job_id}"
                    posted_at = time_el.get("datetime", "") if time_el else ""

                    if not title:
                        continue

                    # Fetch description (rate-limit friendly â€" small delay)
                    description = fetch_linkedin_description(job_id)
                    time.sleep(0.3)

                    jobs.append(normalize_job(
                        source="linkedin",
                        job_id=job_id,
                        company=company,
                        title=title,
                        location=job_location,
                        url=job_url,
                        description=description,
                        posted_at=posted_at,
                    ))
                    new_this_page += 1
                    kw_count += 1

                    if kw_count >= per_kw:
                        break

                if new_this_page == 0:
                    break  # no more results for this keyword

                start += 25
                time.sleep(0.5)  # polite delay between pages

            except Exception as e:
                print(f"  [LinkedIn] Error for '{keyword}' start={start}: {e}")
                break

        print(f"  [LinkedIn] '{keyword}' â†' {len(jobs)} total so far")

    return jobs


# ---------------------------------------------------------------------------
# Source 2: Adzuna free API
# ---------------------------------------------------------------------------

# Mapping from common location names to Adzuna country codes
_ADZUNA_COUNTRY_MAP = {
    "united states": "us", "usa": "us", "us": "us",
    "india": "in", "in": "in",
    "united kingdom": "gb", "uk": "gb", "gb": "gb",
    "canada": "ca", "ca": "ca",
    "australia": "au", "au": "au",
    "germany": "de", "de": "de",
    "france": "fr", "fr": "fr",
    "netherlands": "nl", "nl": "nl",
    "singapore": "sg", "sg": "sg",
    "new zealand": "nz", "nz": "nz",
    "brazil": "br", "br": "br",
    "mexico": "mx", "mx": "mx",
    "south africa": "za", "za": "za",
    "poland": "pl", "pl": "pl",
    "russia": "ru", "ru": "ru",
}


def fetch_adzuna(keywords, max_results, location: str = "United States"):
    """Adzuna REST API -- free, no auth friction."""
    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        print("  [Adzuna] Credentials not set, skipping.")
        return []

    country_code = _ADZUNA_COUNTRY_MAP.get(location.lower().strip(), "us")

    jobs = []
    for keyword in keywords:
        try:
            url = (
                f"https://api.adzuna.com/v1/api/jobs/{country_code}/search/1"
                f"?app_id={ADZUNA_APP_ID}&app_key={ADZUNA_APP_KEY}"
                f"&what={requests.utils.quote(keyword)}"
                f"&max_days_old=1&results_per_page={max_results}"
                "&content-type=application/json"
            )
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            for item in data.get("results", []):
                jobs.append(normalize_job(
                    source="adzuna",
                    job_id=item.get("id", ""),
                    company=item.get("company", {}).get("display_name", ""),
                    title=item.get("title", ""),
                    location=item.get("location", {}).get("display_name", ""),
                    url=item.get("redirect_url", ""),
                    description=item.get("description", ""),
                    posted_at=(item.get("created", "") or "")[:10],
                ))
        except Exception as e:
            print(f"  [Adzuna] Error for '{keyword}': {e}")
    return jobs


# ---------------------------------------------------------------------------
# Source 3: Greenhouse board API (company-specific, free, no key needed)
# ---------------------------------------------------------------------------

def fetch_greenhouse(keywords, company_slugs):
    """Query Greenhouse boards for known AI/tech companies."""
    jobs = []
    kw_lower = [k.lower() for k in keywords]

    for slug in company_slugs:
        try:
            url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
            resp = requests.get(url, timeout=15)
            if resp.status_code != 200:
                continue
            data = resp.json()
            company_name = data.get("name", slug)
            for job in data.get("jobs", []):
                title = job.get("title", "")
                # Only include if title matches a keyword
                if not any(kw in title.lower() for kw in kw_lower):
                    continue
                jobs.append(normalize_job(
                    source="greenhouse",
                    job_id=job.get("id", ""),
                    company=company_name,
                    title=title,
                    location=job.get("location", {}).get("name", ""),
                    url=job.get("absolute_url", ""),
                    description=job.get("content", ""),
                    posted_at=(job.get("updated_at", "") or "")[:10],
                ))
        except Exception as e:
            print(f"  [Greenhouse] Error for '{slug}': {e}")
    return jobs


# ---------------------------------------------------------------------------
# Source 4: Lever board API (public, no key needed)
# ---------------------------------------------------------------------------

def fetch_lever(keywords: list, company_slugs: list) -> list:
    """
    Lever public jobs API -- no auth required.
    Endpoint: https://api.lever.co/v0/postings/{slug}?mode=json&limit=50
    Companies using Lever: Figma, Notion, Vercel, Airbnb, Lyft, Linear, etc.
    """
    jobs = []
    kw_lower = [k.lower() for k in keywords]

    for slug in company_slugs:
        try:
            offset = 0
            limit = 50
            while True:
                url = f"https://api.lever.co/v0/postings/{slug}?mode=json&limit={limit}&offset={offset}"
                resp = requests.get(url, headers=HEADERS, timeout=15)
                if resp.status_code != 200:
                    break
                data = resp.json()
                if not isinstance(data, list) or not data:
                    break
                for job in data:
                    title = job.get("text", "")
                    if not any(kw in title.lower() for kw in kw_lower):
                        continue
                    categories = job.get("categories", {})
                    commitment = categories.get("commitment", "")
                    if "intern" in commitment.lower():
                        continue
                    job_location = categories.get("location", "") or job.get("workplaceType", "")
                    description_html = ""
                    lists = job.get("lists", [])
                    for section in lists:
                        description_html += section.get("text", "") + "\n" + section.get("content", "") + "\n"
                    description_html += job.get("descriptionPlain", "") or ""
                    jobs.append(normalize_job(
                        source="lever",
                        job_id=job.get("id", ""),
                        company=job.get("company", slug),
                        title=title,
                        location=job_location,
                        url=job.get("hostedUrl", ""),
                        description=description_html.strip(),
                        posted_at="",
                    ))
                offset += limit
                if len(data) < limit:
                    break
                time.sleep(0.3)
        except Exception as e:
            print(f"  [Lever] Error for '{slug}': {e}")
    return jobs


# ---------------------------------------------------------------------------
# Source 5: Ashby board API (public, no key needed)
# ---------------------------------------------------------------------------

def fetch_ashby(keywords: list, company_slugs: list) -> list:
    """
    Ashby public jobs API -- no auth required.
    Endpoint: POST https://api.ashbyhq.com/posting-api/job-board/{slug}
    Companies using Ashby: Anthropic, Linear, Rippling, Ramp, Loom, Retool, etc.
    """
    jobs = []
    kw_lower = [k.lower() for k in keywords]

    for slug in company_slugs:
        try:
            url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
            resp = requests.post(
                url,
                json={"includeCompensation": False},
                headers={**HEADERS, "Content-Type": "application/json"},
                timeout=15,
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            postings = data.get("jobPostings", [])
            for job in postings:
                title = job.get("title", "")
                if not any(kw in title.lower() for kw in kw_lower):
                    continue
                employment_type = job.get("employmentType", "")
                if "intern" in employment_type.lower():
                    continue
                location_name = ""
                locations = job.get("jobPostingLocations", [])
                if locations:
                    location_name = locations[0].get("locationName", "")
                description = job.get("descriptionPlain", "") or job.get("descriptionHtml", "") or ""
                jobs.append(normalize_job(
                    source="ashby",
                    job_id=job.get("id", ""),
                    company=slug,
                    title=title,
                    location=location_name,
                    url=job.get("jobUrl", ""),
                    description=description,
                    posted_at=(job.get("publishedAt", "") or "")[:10],
                ))
        except Exception as e:
            print(f"  [Ashby] Error for '{slug}': {e}")
    return jobs


# ---------------------------------------------------------------------------
# Source 6: Workday career sites (POST JSON API)
# ---------------------------------------------------------------------------

def fetch_workday(keywords: list, workday_companies: list) -> list:
    """
    Workday career sites -- POST JSON API, no auth needed.
    Each company entry is a dict: {slug, wd, site}
    URL: https://{slug}.{wd}.myworkdayjobs.com/wday/cxs/{slug}/{site}/jobs
    """
    jobs = []
    kw_lower = [k.lower() for k in keywords]

    for company in workday_companies:
        slug = company.get("slug", "")
        wd = company.get("wd", "wd5")
        site = company.get("site", "")
        name = company.get("name", slug)
        if not slug or not site:
            continue
        try:
            base_url = f"https://{slug}.{wd}.myworkdayjobs.com"
            api_url = f"{base_url}/wday/cxs/{slug}/{site}/jobs"
            offset = 0
            limit = 20
            while True:
                resp = requests.post(
                    api_url,
                    json={"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": ""},
                    headers={**HEADERS, "Content-Type": "application/json"},
                    timeout=20,
                )
                if resp.status_code != 200:
                    break
                data = resp.json()
                postings = data.get("jobPostings", [])
                if not postings:
                    break
                for job in postings:
                    title = job.get("title", "")
                    if not any(kw in title.lower() for kw in kw_lower):
                        continue
                    ext_path = job.get("externalPath", "")
                    job_url = f"{base_url}/en-US{ext_path}" if ext_path else ""
                    jobs.append(normalize_job(
                        source="workday",
                        job_id=ext_path.split("/")[-1] if ext_path else "",
                        company=name,
                        title=title,
                        location=job.get("locationsText", ""),
                        url=job_url,
                        description=job.get("bulletFields", [""])[0] if job.get("bulletFields") else "",
                        posted_at=(job.get("postedOn", "") or "")[:10],
                    ))
                total = data.get("total", 0)
                offset += limit
                if offset >= total or offset >= 500:
                    break
                time.sleep(0.3)
        except Exception as e:
            print(f"  [Workday] Error for '{slug}': {e}")
    return jobs


# ---------------------------------------------------------------------------
# Source 7: SmartRecruiters public Posting API
# ---------------------------------------------------------------------------

def fetch_smartrecruiters(keywords: list, company_ids: list) -> list:
    """
    SmartRecruiters Posting API -- public GET, no auth.
    Endpoint: https://api.smartrecruiters.com/v1/companies/{id}/postings
    """
    jobs = []
    kw_lower = [k.lower() for k in keywords]

    for company_id in company_ids:
        try:
            offset = 0
            limit = 100
            while True:
                url = (
                    f"https://api.smartrecruiters.com/v1/companies/{company_id}/postings"
                    f"?limit={limit}&offset={offset}"
                )
                resp = requests.get(url, headers=HEADERS, timeout=15)
                if resp.status_code != 200:
                    break
                data = resp.json()
                postings = data.get("content", [])
                if not postings:
                    break
                for job in postings:
                    title = job.get("name", "")
                    if not any(kw in title.lower() for kw in kw_lower):
                        continue
                    loc = job.get("location", {})
                    location_str = loc.get("city", "")
                    if loc.get("region"):
                        location_str += f", {loc['region']}"
                    if loc.get("country"):
                        location_str += f", {loc['country']}"
                    if loc.get("remote"):
                        location_str = "Remote" + (f" -- {location_str}" if location_str else "")
                    company_info = job.get("company", {})
                    company_name = company_info.get("name", company_id)
                    ref_url = job.get("ref", "")
                    posting_id = job.get("id", "")
                    jobs.append(normalize_job(
                        source="smartrecruiters",
                        job_id=posting_id,
                        company=company_name,
                        title=title,
                        location=location_str.strip(", "),
                        url=ref_url,
                        description="",
                        posted_at=(job.get("releasedDate", "") or "")[:10],
                    ))
                total = data.get("totalFound", 0)
                offset += limit
                if offset >= total:
                    break
                time.sleep(0.3)
        except Exception as e:
            print(f"  [SmartRecruiters] Error for '{company_id}': {e}")
    return jobs


# ---------------------------------------------------------------------------
# Source 8: Workable public widget API
# ---------------------------------------------------------------------------

def fetch_workable(keywords: list, company_slugs: list) -> list:
    """
    Workable public widget API -- GET, no auth.
    Endpoint: https://www.workable.com/api/accounts/{slug}?details=true
    """
    jobs = []
    kw_lower = [k.lower() for k in keywords]

    for slug in company_slugs:
        try:
            url = f"https://www.workable.com/api/accounts/{slug}?details=true"
            resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
            if resp.status_code != 200:
                continue
            data = resp.json()
            company_name = data.get("name", slug)
            for job in data.get("jobs", []):
                title = job.get("title", "")
                if not any(kw in title.lower() for kw in kw_lower):
                    continue
                location_parts = [job.get("city", ""), job.get("state", ""), job.get("country", "")]
                location_str = ", ".join(p for p in location_parts if p)
                if job.get("telecommuting"):
                    location_str = "Remote" + (f" -- {location_str}" if location_str else "")
                job_url = job.get("url", "") or job.get("shortlink", "")
                jobs.append(normalize_job(
                    source="workable",
                    job_id=job.get("shortcode", ""),
                    company=company_name,
                    title=title,
                    location=location_str,
                    url=job_url,
                    description=job.get("description", ""),
                    posted_at=(job.get("published_on", "") or "")[:10],
                ))
        except Exception as e:
            print(f"  [Workable] Error for '{slug}': {e}")
    return jobs


# ---------------------------------------------------------------------------
# Source 9: BambooHR public careers API (undocumented)
# ---------------------------------------------------------------------------

def fetch_bamboohr(keywords: list, company_slugs: list) -> list:
    """
    BambooHR public careers -- tries JSON endpoint first, falls back to HTML parsing.
    JSON: https://{company}.bamboohr.com/careers/list (Accept: application/json)
    HTML: https://{company}.bamboohr.com/careers (parse with BeautifulSoup)
    """
    jobs = []
    kw_lower = [k.lower() for k in keywords]

    for slug in company_slugs:
        try:
            fetched = _fetch_bamboohr_json(slug, kw_lower)
            if not fetched:
                fetched = _fetch_bamboohr_html(slug, kw_lower)
            jobs.extend(fetched)
        except Exception as e:
            print(f"  [BambooHR] Error for '{slug}': {e}")
    return jobs


def _fetch_bamboohr_json(slug: str, kw_lower: list) -> list:
    url = f"https://{slug}.bamboohr.com/careers/list"
    resp = requests.get(url, headers={**HEADERS, "Accept": "application/json"}, timeout=15)
    if resp.status_code != 200 or "json" not in resp.headers.get("content-type", ""):
        return []
    data = resp.json()
    result_list = data if isinstance(data, list) else data.get("result", [])
    jobs = []
    for job in result_list:
        title = job.get("jobOpeningName", "") or job.get("title", "")
        if not any(kw in title.lower() for kw in kw_lower):
            continue
        loc = job.get("location", {})
        if isinstance(loc, dict):
            location_str = f"{loc.get('city', '')}, {loc.get('state', '')}".strip(", ")
        else:
            location_str = str(loc)
        job_id = str(job.get("id", ""))
        jobs.append(normalize_job(
            source="bamboohr",
            job_id=job_id,
            company=slug,
            title=title,
            location=location_str,
            url=f"https://{slug}.bamboohr.com/careers/{job_id}",
            description=job.get("description", ""),
            posted_at=(job.get("dateCreated", "") or "")[:10],
        ))
    return jobs


def _fetch_bamboohr_html(slug: str, kw_lower: list) -> list:
    url = f"https://{slug}.bamboohr.com/careers"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    if resp.status_code != 200:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    jobs = []
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if "/careers/" not in href or "/detail" in href:
            continue
        title = link.get_text(strip=True)
        if not title or not any(kw in title.lower() for kw in kw_lower):
            continue
        job_id_match = re.search(r"/careers/(\d+)", href)
        job_id = job_id_match.group(1) if job_id_match else ""
        job_url = href if href.startswith("http") else f"https://{slug}.bamboohr.com{href}"
        parent = link.find_parent("div") or link.find_parent("li")
        location_str = ""
        if parent:
            loc_el = parent.find(class_=re.compile(r"location|loc", re.I))
            if loc_el:
                location_str = loc_el.get_text(strip=True)
        jobs.append(normalize_job(
            source="bamboohr",
            job_id=job_id,
            company=slug,
            title=title,
            location=location_str,
            url=job_url,
            description="",
            posted_at="",
        ))
    return jobs


def fetch_all():
    config = load_config()
    keywords = config["keywords"]
    location = config["filters"]["location"]
    max_results = config["filters"]["max_results"]
    greenhouse_companies = config.get("greenhouse_companies", [])
    lever_companies = config.get("lever_companies", [])
    ashby_companies = config.get("ashby_companies", [])
    workday_companies = config.get("workday_companies", [])
    smartrecruiters_companies = config.get("smartrecruiters_companies", [])
    workable_companies = config.get("workable_companies", [])
    bamboohr_companies = config.get("bamboohr_companies", [])

    all_jobs = []

    # ── Auto-apply platforms first (these jobs can be submitted automatically) ──

    # --- Greenhouse (form + Gmail verification) ---
    if greenhouse_companies:
        print(f"[fetch] Fetching from Greenhouse ({len(greenhouse_companies)} companies)...")
        gh_jobs = fetch_greenhouse(keywords, greenhouse_companies)
        print(f"  [Greenhouse] Returned {len(gh_jobs)} jobs")
        all_jobs.extend(gh_jobs)

    # --- Lever (REST API apply) ---
    if lever_companies:
        print(f"[fetch] Fetching from Lever ({len(lever_companies)} companies)...")
        lever_jobs = fetch_lever(keywords, lever_companies)
        print(f"  [Lever] Returned {len(lever_jobs)} jobs")
        all_jobs.extend(lever_jobs)

    # --- Ashby (REST API apply) ---
    if ashby_companies:
        print(f"[fetch] Fetching from Ashby ({len(ashby_companies)} companies)...")
        ashby_jobs = fetch_ashby(keywords, ashby_companies)
        print(f"  [Ashby] Returned {len(ashby_jobs)} jobs")
        all_jobs.extend(ashby_jobs)

    # --- Workday (form scraping) ---
    if workday_companies:
        print(f"[fetch] Fetching from Workday ({len(workday_companies)} companies)...")
        wd_jobs = fetch_workday(keywords, workday_companies)
        print(f"  [Workday] Returned {len(wd_jobs)} jobs")
        all_jobs.extend(wd_jobs)

    # --- SmartRecruiters (form scraping) ---
    if smartrecruiters_companies:
        print(f"[fetch] Fetching from SmartRecruiters ({len(smartrecruiters_companies)} companies)...")
        sr_jobs = fetch_smartrecruiters(keywords, smartrecruiters_companies)
        print(f"  [SmartRecruiters] Returned {len(sr_jobs)} jobs")
        all_jobs.extend(sr_jobs)

    # --- Workable (form scraping) ---
    if workable_companies:
        print(f"[fetch] Fetching from Workable ({len(workable_companies)} companies)...")
        wk_jobs = fetch_workable(keywords, workable_companies)
        print(f"  [Workable] Returned {len(wk_jobs)} jobs")
        all_jobs.extend(wk_jobs)

    # --- BambooHR (form scraping) ---
    if bamboohr_companies:
        print(f"[fetch] Fetching from BambooHR ({len(bamboohr_companies)} companies)...")
        bhr_jobs = fetch_bamboohr(keywords, bamboohr_companies)
        print(f"  [BambooHR] Returned {len(bhr_jobs)} jobs")
        all_jobs.extend(bhr_jobs)

    print(f"\n[fetch] Auto-apply sources: {len(all_jobs)} jobs")

    # ── Passive sources (manual apply only) ────────────────────────────────────

    # --- LinkedIn: Apify + direct guest API both run; results merged by URL ---
    print("[fetch] Fetching LinkedIn jobs (Apify)...")
    apify_jobs = fetch_linkedin_apify(keywords, max_results, location=location)
    print(f"  [Apify] Returned {len(apify_jobs)} jobs")

    print("[fetch] Fetching LinkedIn jobs (direct guest API)...")
    direct_jobs = fetch_linkedin_direct(keywords, max_results, location=location)
    print(f"  [LinkedIn direct] Returned {len(direct_jobs)} jobs")

    # Merge: Apify first, then fill in any new URLs from direct
    seen_linkedin_urls: set = {j["url"] for j in apify_jobs if j["url"]}
    merged_linkedin = list(apify_jobs)
    for j in direct_jobs:
        if j["url"] and j["url"] not in seen_linkedin_urls:
            seen_linkedin_urls.add(j["url"])
            merged_linkedin.append(j)
    print(f"  [LinkedIn merged] Total unique: {len(merged_linkedin)} jobs")
    all_jobs.extend(merged_linkedin)

    # --- Adzuna ---
    print("[fetch] Fetching from Adzuna...")
    adzuna_jobs = fetch_adzuna(keywords, max_results, location=location)
    print(f"  [Adzuna] Returned {len(adzuna_jobs)} jobs")
    all_jobs.extend(adzuna_jobs)

    with open(RAW_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(all_jobs, f, indent=2, ensure_ascii=False)

    print(f"\n[fetch] Total raw jobs: {len(all_jobs)} -> saved to {RAW_OUTPUT}")
    return all_jobs


if __name__ == "__main__":
    fetch_all()

