# resume parsing and llm as a judge for job matching
import time
import openai
from loguru import logger
from pydantic import BaseModel
from jobs_radar.models import ParsedResume, ParseResumeRequest, ParsedResumeResponse, ScrapedJob

_client: openai.AsyncOpenAI | None = None


def _get_client() -> openai.AsyncOpenAI:
    from jobs_radar.config import settings
    global _client
    if _client is None:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        _client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


class _Rating(BaseModel):
    rating: int
    reason: str


async def parse_resume(request: ParseResumeRequest) -> ParsedResumeResponse:
    start = time.perf_counter()
    response = await _get_client().beta.chat.completions.parse(
        model=request.model,
        temperature=0,
        response_format=ParsedResume,
        messages=[
            {"role": "system", "content": "Extract structured resume information. Return only the JSON."},
            {"role": "user", "content": request.resume_text},
        ],
    )
    return ParsedResumeResponse(
        parsed_resume=response.choices[0].message.parsed,
        model_used=response.model,
        parsing_time_seconds=round(time.perf_counter() - start, 3),
    )


async def rate_job(system_prompt: str, model: str) -> dict:
    try:
        response = await _get_client().beta.chat.completions.parse(
            model=model,
            temperature=0,
            max_tokens=120,
            response_format=_Rating,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Rate this job."},
            ],
        )
        return response.choices[0].message.parsed.model_dump()
    except Exception as e:
        logger.warning(f"rate_job failed: {e}")
        return {"rating": None, "reason": None}


def build_judge_prompt(
    parsed_resume: ParsedResume,
    job: ScrapedJob,
    liked: list = None,
    disliked: list = None,
) -> str:
    examples = ""
    if liked:
        examples += "\nExamples of jobs the candidate liked:\n"
        for e in liked:
            examples += f"  - {e.title} @ {e.company} (rating: {e.rating}/5): {e.notes or 'no notes'}\n"
    if disliked:
        examples += "\nExamples of jobs the candidate disliked:\n"
        for e in disliked:
            examples += f"  - {e.title} @ {e.company} (rating: {e.rating}/5): {e.notes or 'no notes'}\n"

    return f"""
You are a job matching assistant. Rate how well the candidate matches the job on a scale of 1 to 10.

Rating scale:
10 = perfect match (role, skills, seniority all align)
7-9 = strong match with minor gaps
4-6 = partial match, significant gaps
1-3 = poor match

Output ONLY valid JSON in this exact format:
{{"rating": <1-10>, "reason": "<one sentence>"}}
{examples}
Candidate Resume:
- Target Roles: {', '.join(parsed_resume.target_roles)}
- Excluded Roles: {', '.join(parsed_resume.excluded_roles)}
- Core Skills: {', '.join(parsed_resume.core_skills)}
- Seniority: {', '.join(parsed_resume.seniority)}
- Years of Experience: {parsed_resume.years_experience or 'N/A'}
- Education Level: {parsed_resume.education_level or 'N/A'}
- Summary: {parsed_resume.summary or 'N/A'}

Job:
- Title: {job.title}
- Company: {job.company}
- Location: {job.location or 'N/A'}
- Description: {' '.join((job.description or '').split()[:500]) or 'N/A'}
"""