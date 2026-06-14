# qdrant in-memory vector store : setup, upsert, hybrid RRF search
from loguru import logger
from fastembed import TextEmbedding, SparseTextEmbedding
from qdrant_client import QdrantClient, models
from jobs_radar.models import SearchFilters

COLLECTION   = "jobs"
DENSE_MODEL  = "BAAI/bge-small-en-v1.5"
SPARSE_MODEL = "Qdrant/bm25"
DENSE_SIZE   = 384

_dense_model: TextEmbedding | None = None
_sparse_model: SparseTextEmbedding | None = None


def _dense() -> TextEmbedding:
    global _dense_model
    if _dense_model is None:
        _dense_model = TextEmbedding(DENSE_MODEL)
    return _dense_model


def _sparse() -> SparseTextEmbedding:
    global _sparse_model
    if _sparse_model is None:
        _sparse_model = SparseTextEmbedding(SPARSE_MODEL)
    return _sparse_model


def make_client():
    return QdrantClient(":memory:")


def setup_collection(client: QdrantClient):
    if COLLECTION not in client.get_collections().collections:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config={
                "dense": models.VectorParams(size=DENSE_SIZE, distance=models.Distance.COSINE),
            },
            sparse_vectors_config={
                "sparse": models.SparseVectorParams(modifier=models.Modifier.IDF),
            }
        )
        logger.info(f"Created collection '{COLLECTION}' with dense vector config.")
    else:
        logger.info(f"Collection '{COLLECTION}' already exists.")


def upsert_jobs(client: QdrantClient, jobs: list[dict]):
    texts = [
        (f"{job.get('title', '')} {job.get('description', '') or ''}".strip()
         or job.get('company', 'unknown position'))
        for job in jobs
    ]

    dense_vecs = list(_dense().embed(texts))
    sparse_vecs = list(_sparse().embed(texts))

    points = [
        models.PointStruct(
            id=idx,
            vector={
                "dense": dense_vecs[idx].tolist(),
                "sparse": models.SparseVector(
                    indices=sparse_vecs[idx].indices.tolist(),
                    values=sparse_vecs[idx].values.tolist(),
                ),
            },
            payload={
                "title": job["title"],
                "company": job["company"],
                "location": job.get("location"),
                "job_url": job.get("job_url"),
                "date_posted": job.get("date_posted"),
                "description": job.get("description"),
                "is_senior": job.get("is_senior", False),
                "has_clearance": job.get("has_clearance", False),
                "is_entry_level": job.get("is_entry_level", False),
                "is_remote": job.get("is_remote", False),
                "experience_required": job.get("experience_required"),
            }
        )
        for idx, job in enumerate(jobs)
    ]
    client.upsert(collection_name=COLLECTION, points=points)
    logger.info(f"Upserted {len(points)} jobs into collection '{COLLECTION}'.")


def search_jobs(client: QdrantClient, query: str, limit: int = 100, filters: SearchFilters = None) -> list[tuple[dict, float]]:
    filters = filters or SearchFilters()
    must, must_not = [], []

    if filters.entry_level_only:
        must.append(models.FieldCondition(key="is_entry_level", match=models.MatchValue(value=True)))
    if filters.remote_only:
        must.append(models.FieldCondition(key="is_remote", match=models.MatchValue(value=True)))
    if filters.exclude_senior:
        must_not.append(models.FieldCondition(key="is_senior", match=models.MatchValue(value=True)))
    if filters.exclude_clearance:
        must_not.append(models.FieldCondition(key="has_clearance", match=models.MatchValue(value=True)))

    exclusion_filter = models.Filter(must=must, must_not=must_not)

    dense_query = list(_dense().embed([query]))[0].tolist()
    sparse_result = list(_sparse().embed([query]))[0]
    sparse_query = models.SparseVector(
        indices=sparse_result.indices.tolist(),
        values=sparse_result.values.tolist(),
    )

    results = client.query_points(
        collection_name=COLLECTION,
        prefetch=[
            models.Prefetch(
                query=dense_query,
                using="dense",
                filter=exclusion_filter,
                limit=limit * 5,
            ),
            models.Prefetch(
                query=sparse_query,
                using="sparse",
                filter=exclusion_filter,
                limit=limit * 5,
            ),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=limit,
        with_payload=True,
    )
    return [(hit.payload, hit.score) for hit in results.points]
