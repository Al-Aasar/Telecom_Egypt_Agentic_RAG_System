import os
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

from db import get_connection

load_dotenv()

EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
TS_CONFIG = os.getenv("TS_CONFIG", "simple")

DENSE_TOP_K = int(os.getenv("DENSE_TOP_K", 15))
SPARSE_TOP_K = int(os.getenv("SPARSE_TOP_K", 15))
FINAL_TOP_K = int(os.getenv("FINAL_TOP_K", 6))
RRF_K = int(os.getenv("RRF_K", 60))

MIN_DENSE_SCORE = float(os.getenv("MIN_DENSE_SCORE", 0.35))

_model = None


def get_model():
    """Lazy singleton so the embedding model loads once per process,
    not once per request."""
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _model


def dense_search(query: str, top_k: int = DENSE_TOP_K):
    model = get_model()
    query_vec = model.encode([query], normalize_embeddings=True)[0].tolist()

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, url, title, chunk_text,
                   1 - (embedding <=> %s::vector) AS score
            FROM document_vectors
            ORDER BY embedding <=> %s::vector
            LIMIT %s;
            """,
            (query_vec, query_vec, top_k),
        )
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    return [
        {"id": r[0], "url": r[1], "title": r[2], "chunk_text": r[3], "dense_score": r[4]}
        for r in rows
        if r[4] >= MIN_DENSE_SCORE
    ]


def sparse_search(query: str, top_k: int = SPARSE_TOP_K):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            f"""
            SELECT id, url, title, chunk_text,
                   ts_rank_cd(chunk_tsv, plainto_tsquery('{TS_CONFIG}', %s)) AS score
            FROM document_vectors
            WHERE chunk_tsv @@ plainto_tsquery('{TS_CONFIG}', %s)
            ORDER BY score DESC
            LIMIT %s;
            """,
            (query, query, top_k),
        )
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    return [
        {"id": r[0], "url": r[1], "title": r[2], "chunk_text": r[3], "sparse_score": r[4]}
        for r in rows
    ]


def reciprocal_rank_fusion(dense_results, sparse_results, k: int = RRF_K):
    """Combines two ranked lists without needing to normalize dense
    cosine-similarity scores against sparse ts_rank scores, which live
    on different, incompatible scales. Each result's fused score is
    1 / (k + rank_in_list), summed across whichever list(s) it appears in.
    """
    fused = {}

    for rank, item in enumerate(dense_results):
        entry = fused.setdefault(item["id"], {**item, "rrf_score": 0.0})
        entry["rrf_score"] += 1.0 / (k + rank + 1)

    for rank, item in enumerate(sparse_results):
        entry = fused.setdefault(item["id"], {**item, "rrf_score": 0.0})
        entry["rrf_score"] += 1.0 / (k + rank + 1)

        entry.setdefault("dense_score", None)
        entry["sparse_score"] = item["sparse_score"]

    return sorted(fused.values(), key=lambda x: x["rrf_score"], reverse=True)


def hybrid_search(query: str, top_k: int = FINAL_TOP_K):
    dense_results = dense_search(query, DENSE_TOP_K)
    sparse_results = sparse_search(query, SPARSE_TOP_K)
    fused = reciprocal_rank_fusion(dense_results, sparse_results)
    return fused[:top_k]


if __name__ == "__main__":
    import sys

    q = " ".join(sys.argv[1:]) or "test query"
    for r in hybrid_search(q):
        print(f"[{r['rrf_score']:.4f}] {r['title']} — {r['url']}")
        print(r["chunk_text"][:150].replace("\n", " "), "...\n")
