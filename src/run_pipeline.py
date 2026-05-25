"""
run_pipeline.py
Orchestrates the full pipeline: fetch -> filter -> dedupe -> save -> rank.
Run manually:  python run_pipeline.py
Scheduled:     Windows Task Scheduler calls this script daily.
"""
import os
import sys
import traceback
from datetime import datetime

# Ensure src/ modules are importable regardless of cwd
_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
_BASE_DIR = os.path.dirname(_SRC_DIR)
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

# JSON files that are regenerated each run — cleared before every pipeline start
_OUTPUT_DIR = os.path.join(_BASE_DIR, "output")
_STALE_FILES = [
    "raw_jobs.json",
    "filtered_jobs.json",
    "deduped_jobs.json",
    "top25_jobs.json",
]

STEPS = [
    ("Fetching jobs",          "fetch_jobs",    "fetch_all"),
    ("Filtering jobs",         "filter_jobs",   "filter_jobs"),
    ("Deduplicating jobs",     "dedupe_jobs",   "dedupe_jobs"),
    ("Saving to SQLite",       "save_to_sqlite","save_jobs"),
    ("AI ranking (top 25)",    "ai_ranker",     "rank_jobs"),
]


def clear_outputs():
    """Delete all stale JSON files from a previous run before starting fresh."""
    print("--- Clearing previous output files ---")
    for fname in _STALE_FILES:
        fpath = os.path.join(_OUTPUT_DIR, fname)
        if os.path.exists(fpath):
            os.remove(fpath)
            print(f"  Removed: {fname}")
        else:
            print(f"  Skipped (not found): {fname}")
    print()


def run_pipeline():
    start = datetime.now()
    print(f"\n{'=' * 60}")
    print(f"  Job Hunter Pipeline - {start.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}\n")

    clear_outputs()

    for label, module_name, func_name in STEPS:
        print(f"--- {label} ---")
        try:
            import importlib
            module = importlib.import_module(module_name)
            fn = getattr(module, func_name)
            fn()
            print()
        except Exception:
            print(f"\n[ERROR] Step '{label}' failed:")
            traceback.print_exc()
            print("\nPipeline aborted.")
            sys.exit(1)

    elapsed = (datetime.now() - start).seconds
    print(f"{'=' * 60}")
    print(f"  Pipeline completed in {elapsed}s - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    run_pipeline()
