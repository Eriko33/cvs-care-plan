"""Semantic (embedding-based) search over indexed document chunks.

Usage:
    from rag.search import search
    results = search("IVIG renal function risk", top_k=5)
"""
import os

import django
from django.apps import apps

# Allow `python -m rag.search` to run standalone (outside a request that
# already configured Django), while staying a no-op when imported from
# code that's already running inside the Django app.
if not apps.apps_ready:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()

from pgvector.django import CosineDistance  # noqa: E402

from .embeddings import embed_text  # noqa: E402
from .models import DocumentChunk  # noqa: E402


def search(query: str, top_k: int = 5, drug_name: str | None = None) -> list[DocumentChunk]:
    query_vector = embed_text(query)

    qs = DocumentChunk.objects.all()
    if drug_name:
        qs = qs.filter(drug_name=drug_name)

    return list(
        qs.annotate(distance=CosineDistance("embedding", query_vector))
        .order_by("distance")[:top_k]
    )


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    query_text = sys.argv[1]
    for chunk in search(query_text):
        print(f"[{chunk.distance:.4f}] {chunk.drug_name} — {chunk.section_name}")
        print(chunk.text[:200].replace("\n", " "))
        print()
