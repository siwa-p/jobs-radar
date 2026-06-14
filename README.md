# Jobs Radar

Personalised job search pipeline: scrape → tag → embed → rank → rate.

## Features

- **Resume parsing** — paste raw resume text, get structured output (target roles, skills, seniority, experience) via OpenAI structured outputs
- **Parallel scraping** — scrapes Indeed across multiple queries and locations concurrently using `ThreadPoolExecutor`
- **Dedup + tagging** — removes duplicate listings, tags each job for seniority, entry-level, remote, clearance, and experience range using regex
- **Hybrid vector search** — dense (BGE) + sparse (BM25) search with Reciprocal Rank Fusion via Qdrant in-memory
- **LLM-as-judge rating** — each result is scored 1–10 against the candidate's resume using `gpt-4o-mini`
- **Feedback loop** — rate jobs 1–5 stars; liked/disliked examples are injected into the judge prompt on future searches to personalise ratings over time
- **Single-table persistence** — search results and user feedback live in one SQLite table (`job_results`), keyed by `job_url`; re-submitting feedback updates the row, no duplicates
- **CSV export** — every scrape is auto-saved to `~/.jobs-radar/jobs_{timestamp}.csv`, downloadable from the UI
- **Streamlit UI** — parse resume, search jobs with inline feedback, browse and rate recent results
- **REST API** — FastAPI backend, useful for scripting or other clients

## Stack

- Python 3.12, FastAPI, Streamlit
- OpenAI API (`gpt-4o-mini` by default)
- Qdrant (in-memory) + fastembed
- jobspy (Indeed scraping)
- SQLite (results + feedback storage)
- uv (dependency management)

## Installation

```bash
pip install jobs-radar
# or with uv
uv add jobs-radar
```

Or run from source:

```bash
git clone https://github.com/siwa-p/jobs-radar.git
cd jobs-radar
uv sync
```

## Setup

```bash
cp .env.example .env  # fill in OPENAI_API_KEY
```

Data (SQLite DB + CSVs) is stored in `~/.jobs-radar/` by default. Override with `DATA_DIR` in your `.env`.

## Running

You need two terminals — one for the API server and one for the UI.

**From a pip/uv install:**

```bash
# terminal 1 — start the API server
jobs-radar-serve

# terminal 2 — open the UI
jobs-radar-ui
```

**From source:**

```bash
# terminal 1 — API
uvicorn jobs_radar.main:app --reload

# terminal 2 — UI
streamlit run jobs_radar/ui.py
```

Then open `http://localhost:8501` in your browser. API docs at `http://localhost:8000/docs`.

## Configuration

All settings are read from environment variables or a `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | Required |
| `DATA_DIR` | `~/.jobs-radar` | Where SQLite DB and CSVs are stored |
| `API_HOST` | `0.0.0.0` | FastAPI bind host |
| `API_PORT` | `8000` | FastAPI port |
| `API_BASE` | `http://localhost:8000` | URL the Streamlit UI uses to reach the API |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/parse` | Parse resume text → structured profile |
| POST | `/search` | Scrape, embed, rank, and rate jobs |
| GET | `/results/recent` | Load the most recent search results |
| POST | `/feedback` | Save user rating for a job |

## Project Structure

```
jobs_radar/
  main.py          # FastAPI routes
  pipeline.py      # scrape, dedup, tag, validate
  vector_store.py  # Qdrant setup, upsert, hybrid search
  llm.py           # resume parsing, job rating, judge prompt
  feedback.py      # SQLite — job_results table, save/load functions
  models.py        # Pydantic models
  config.py        # pydantic-settings — all env/config vars
  cli.py           # jobs-radar-serve and jobs-radar-ui entrypoints
  ui.py            # Streamlit UI
tests/             # pytest suite (54 tests)
```

## Data Model

All results and feedback share one SQLite table (`~/.jobs-radar/feedback.db`):

| Column | Source |
|--------|--------|
| `job_url` (PK) | scraper |
| `title`, `company`, `location`, ... | scraper |
| `llm_rating`, `relevance_score`, `llm_reasoning` | system |
| `user_rating`, `notes` | user feedback |
| `search_id`, `saved_at` | system |

Re-running a search updates system fields for any URL already in the DB while preserving `user_rating` and `notes`.

## Notes

- Qdrant runs in-memory — the vector index is not persisted between server restarts. The SQLite DB and CSV exports are the durable layer.
- fastembed downloads model weights on the first `upsert_jobs` call (~30–60s). Subsequent calls are fast.
