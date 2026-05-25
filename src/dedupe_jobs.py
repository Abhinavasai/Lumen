"""
dedupe_jobs.py
Deduplicates filtered_jobs.json by URL and normalized company|title|location key.
Caps output at config max_results. Outputs deduped_jobs.json.
"""
import json
import os
import re
import yaml

# ── Path resolution ─────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

FILTERED_INPUT = os.path.join(OUTPUT_DIR, "filtered_jobs.json")
DEDUPED_OUTPUT = os.path.join(OUTPUT_DIR, "deduped_jobs.json")


def load_config():
    with open(os.path.join(BASE_DIR, "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def normalize_text(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", text.lower())).strip()


def make_normalized_key(job: dict) -> str:
    company = normalize_text(job.get("company", ""))
    title = normalize_text(job.get("title", ""))
    # Strip common seniority/level words so near-duplicates collapse
    for word in ("new grad", "entry level", "junior", "associate", "ii", "iii", "i"):
        title = title.replace(word, "").strip()
    location = normalize_text(job.get("location", ""))
    return f"{company}|{title}|{location}"


def dedupe_jobs():
    config = load_config()
    max_results = config["filters"]["max_results"]

    with open(FILTERED_INPUT, encoding="utf-8") as f:
        jobs = json.load(f)

    seen_urls: set[str] = set()
    seen_keys: set[str] = set()
    deduped = []

    for job in jobs:
        url = job.get("url", "").strip()
        key = make_normalized_key(job)

        if url and url in seen_urls:
            continue
        if key in seen_keys:
            continue

        if url:
            seen_urls.add(url)
        seen_keys.add(key)

        job["normalized_key"] = key
        deduped.append(job)

        if len(deduped) >= max_results:
            break

    with open(DEDUPED_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(deduped, f, indent=2, ensure_ascii=False)

    print(
        f"[dedupe] {len(jobs)} filtered â†’ {len(deduped)} unique "
        f"(cap: {max_results}) â†’ saved to {DEDUPED_OUTPUT}"
    )
    return deduped


if __name__ == "__main__":
    dedupe_jobs()

