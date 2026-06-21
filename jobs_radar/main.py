import asyncio
import time
from datetime import datetime
import pandas as pd
from fastapi import FastAPI, HTTPException

from jobs_radar.config import settings
from jobs_radar.feedback import get_correlation, load_examples, load_recent, save_feedback, save_results
from jobs_radar.llm import build_judge_prompt, parse_resume, rate_job
from jobs_radar.models import (
    FeedbackRequest,
    FeedbackResponse,
    JobMatch,
    JobSearchRequest,
    ParseResumeRequest,
    ParsedResumeResponse,
    ScrapedJob,
    SearchResponse,
)
from jobs_radar.pipeline import dedup, scrape_parallel, tag_experience, tag_jobs, validate_jobs
from jobs_radar.vector_store import make_client, search_jobs, setup_collection, upsert_jobs

app = FastAPI()


@app.get("/health")
async def health():
    return {"llm_enabled": settings.openai_api_key is not None}


@app.post("/parse", response_model=ParsedResumeResponse)
async def parse(request: ParseResumeRequest):
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="LLM features require OPENAI_API_KEY")
    return await parse_resume(request)


@app.post("/search", response_model=SearchResponse)
async def search(request: JobSearchRequest):
    start = time.perf_counter()

    raw = await asyncio.to_thread(
        scrape_parallel, request.locations, request.queries, request.hours_old
    )
    jobs = await asyncio.to_thread(
        lambda: validate_jobs(tag_experience(tag_jobs(dedup(raw))))
    )

    if not jobs:
        return SearchResponse(
            jobs=[], total_found=0,
            search_time_seconds=round(time.perf_counter() - start, 3),
        )

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = settings.data_dir / f"jobs_{ts}.csv"
    await asyncio.to_thread(lambda: pd.DataFrame(jobs).to_csv(csv_path, index=False))

    qdrant = make_client()
    setup_collection(qdrant)
    await asyncio.to_thread(upsert_jobs, qdrant, jobs)

    if request.parsed_resume:
        query = " ".join(request.parsed_resume.target_roles + request.parsed_resume.core_skills)
    else:
        query = " ".join(request.queries)
    results = search_jobs(qdrant, query, limit=request.top_k, filters=request.filters)

    if not results:
        return SearchResponse(
            jobs=[], total_found=0,
            search_time_seconds=round(time.perf_counter() - start, 3),
            query_used=query,
        )

    scraped = [ScrapedJob(**payload) for payload, _ in results]
    if settings.openai_api_key and request.parsed_resume:
        liked, disliked = load_examples()
        prompts = [build_judge_prompt(request.parsed_resume, job, liked, disliked) for job in scraped]
        ratings = await asyncio.gather(*[rate_job(p, request.model) for p in prompts])
    else:
        ratings = [{"rating": None, "reason": None}] * len(scraped)

    matches = [
        JobMatch(
            job_url=job.job_url,
            title=job.title,
            company=job.company,
            location=job.location,
            description=job.description,
            date_posted=job.date_posted,
            relevance_score=round(score, 4),
            llm_rating=rating["rating"],
            llm_reasoning=rating["reason"],
            experience_required=job.experience_required,
        )
        for (_, score), job, rating in zip(results, scraped, ratings)
    ]
    matches.sort(key=lambda j: (j.llm_rating or 0, j.relevance_score or 0), reverse=True)

    await asyncio.to_thread(save_results, matches, ts)

    return SearchResponse(
        jobs=matches,
        total_found=len(matches),
        search_time_seconds=round(time.perf_counter() - start, 3),
        query_used=query,
    )


@app.get("/results/recent", response_model=list[JobMatch])
async def recent_results():
    rows = await asyncio.to_thread(load_recent)
    if not rows:
        raise HTTPException(status_code=404, detail="No results found. Run a search first.")
    return rows


@app.get("/results/correlation")
async def correlation():
    result = await asyncio.to_thread(get_correlation)
    if result is None:
        raise HTTPException(status_code=404, detail="Not enough rated jobs yet (need at least 3 with both LLM and user ratings).")
    return result


@app.post("/feedback", response_model=FeedbackResponse)
async def feedback(request: FeedbackRequest):
    await asyncio.to_thread(save_feedback, request.job_url, request.user_rating, request.notes)
    return FeedbackResponse(saved=True)
