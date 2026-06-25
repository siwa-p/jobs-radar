# # scrape indeed --> tag --> embed --> rank
from concurrent.futures import ThreadPoolExecutor, as_completed
from itertools import product
import re
import pandas as pd
from jobspy import scrape_jobs
from loguru import logger
from jobs_radar.models import ScrapedJob

_EXP_RE = re.compile(r'(\d+)\s*[-–]\s*(\d+)\s*\+?\s*years?|(\d+)\s*\+\s*years?', re.IGNORECASE)
_SENIOR_RE = re.compile(r'\b(senior|sr\.?|lead|principal|staff)\b', re.IGNORECASE)
_ENTRY_RE = re.compile(r'\b(junior|jr\.?|entry[\s-]level|associate|new\s+grad)\b', re.IGNORECASE)
_REMOTE_RE = re.compile(r'\b(remote|work[\s-]from[\s-]home|wfh|fully[\s-]remote)\b', re.IGNORECASE)
_CLEARANCE_RE = re.compile(r'\b(security\s+clearance|clearance\s+required|top\s+secret|ts/sci|secret\s+clearance)\b', re.IGNORECASE)

def scrape_one(location, query, hours_old=24, site_name="indeed"):
    logger.info(f"Scraping '{query}' jobs in '{location}' posted in the last {hours_old} hours...")
    jobs = scrape_jobs(
        site_name=site_name,
        search_term=query,
        google_search_term=f"{query} jobs near {location} posted in the last {hours_old} hours site {site_name}",
        location=location,
        hours_old=hours_old,
        country_indeed="USA",
        linkedin_fetch_description=True,
    )
    if jobs is not None and len(jobs) > 0:
        logger.info(f"Scraped {len(jobs)} jobs for query '{query}' in location '{location}'.")
    else:
        logger.warning(f"No jobs found for query '{query}' in location '{location}'.")
        return pd.DataFrame()
    return jobs


def scrape_parallel(locations, queries, hours_old=24, site_name="indeed", max_workers=4):
    all_jobs = []
    pairs = list(product(locations, queries))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(scrape_one, loc, q, hours_old, site_name): (loc, q) for loc, q in pairs}
        for future in as_completed(futures):
            jobs = future.result()
            if jobs is not None and len(jobs) > 0:
                all_jobs.extend(jobs.to_dict(orient="records"))
    logger.info(f"Finished scraping. Total jobs scraped: {len(all_jobs)}")
    return all_jobs


def dedup(jobs):
    jobs_df = pd.DataFrame(jobs)
    before_dedup = len(jobs_df)
    jobs_df.drop_duplicates(subset=["job_url"], inplace=True)
    after_dedup = len(jobs_df)
    logger.info(f"Deduplicated jobs: {before_dedup} -> {after_dedup}")
    return jobs_df.to_dict(orient="records")


def tag_jobs(jobs):
    for job in jobs:
        title = job.get("title", "")
        desc = job.get("description", "")
        location = job.get("location", "")
        text = f"{title} {desc} {location}"
        job["is_senior"] = bool(_SENIOR_RE.search(title))
        job["is_entry_level"] = bool(_ENTRY_RE.search(title) or _ENTRY_RE.search(desc))
        job["is_remote"] = bool(_REMOTE_RE.search(text))
        job["has_clearance"] = bool(_CLEARANCE_RE.search(text))
    return jobs


def extract_experience(description: str) -> str | None:
    if not isinstance(description, str) or not description:
        return None
    m = _EXP_RE.search(description)
    if not m:
        return None
    lo, hi = m.group(1) or m.group(3), m.group(2)
    has_plus = '+' in m.group(0).split('year')[0]
    if hi:
        return f"{lo}-{hi}"
    return f"{lo}+" if has_plus else lo


def is_high_experience(exp: str | None) -> bool:
    if not exp:
        return False
    lo = int(re.match(r'\d+', exp).group())
    return lo >= 5


def tag_experience(jobs):
    for job in jobs:
        job["experience_required"] = extract_experience(job.get("description", ""))
    return jobs


def validate_jobs(jobs):
    valid, invalid = [], []
    for job in jobs:
        try:
            cleaned = {k: (None if isinstance(v, float) and pd.isna(v) else v) for k, v in job.items()}
            valid.append(ScrapedJob(**cleaned).model_dump())
        except Exception as e:
            logger.warning(f"Skipping invalid job '{job.get('title', '?')}' @ '{job.get('company', '?')}': {e}")
            invalid.append(job)
    logger.info(f"Validated {len(valid)} jobs, skipped {len(invalid)}")
    return valid


def percentile_rank(scores:list[float]): # map the search scores to a 0 - 100
    sorted_scores = sorted(scores)
    ranks = []
    for s in scores:
        rank = (sorted_scores.index(s) + 1) / len(scores) * 100
        ranks.append(rank)
    return ranks
