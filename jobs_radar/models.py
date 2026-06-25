from pydantic import BaseModel
from datetime import date


class ParsedResume(BaseModel):
    target_roles: list[str]
    excluded_roles: list[str]
    core_skills: list[str]
    seniority: list[str]
    years_experience: int | None = None
    education_level: str | None = None
    summary: str | None = None


class ParsedResumeResponse(BaseModel):
    parsed_resume: ParsedResume
    model_used: str
    parsing_time_seconds: float


class JobSearchRequest(BaseModel):
    parsed_resume: ParsedResume | None = None
    model: str = "gpt-4o-mini"
    queries: list[str]
    locations: list[str]
    hours_old: int = 24
    top_k: int = 10
    entry_level_only: bool = True
    remote_only: bool = True
    exclude_senior: bool = True
    exclude_clearance: bool = True


class ScrapedJob(BaseModel):
    job_url: str
    title: str
    company: str | None = None
    location: str | None = None
    description: str | None = None
    date_posted: date | None = None
    is_senior: bool = False
    is_entry_level: bool = False
    is_remote: bool = False
    has_clearance: bool = False
    experience_required: str | None = None


class JobMatch(BaseModel):
    job_url: str | None = None
    title: str
    company: str
    location: str | None = None
    description: str | None = None
    date_posted: date | None = None
    relevance_score: float | None = None
    llm_rating: int | None = None
    llm_reasoning: str | None = None
    experience_required: str | None = None


class SearchResponse(BaseModel):
    jobs: list[JobMatch]
    total_found: int
    search_time_seconds: float
    query_used: str | None = None


class FeedbackEntry(BaseModel):
    job_url: str
    title: str
    company: str
    rating: int
    notes: str = ""


class FeedbackRequest(BaseModel):
    job_url: str
    user_rating: int
    notes: str = ""


