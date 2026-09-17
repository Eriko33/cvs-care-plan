"""Local, free embedding model — no API key, no external account.

Uses sentence-transformers' all-MiniLM-L6-v2 (384 dimensions): small, fast on
CPU, good enough general-purpose quality for this project's scale.
"""
from sentence_transformers import SentenceTransformer

EMBEDDING_DIM = 384

_model = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def embed_text(text: str) -> list[float]:
    return _get_model().encode(text, normalize_embeddings=True).tolist()


def embed_texts(texts: list[str]) -> list[list[float]]:
    return _get_model().encode(texts, normalize_embeddings=True).tolist()
