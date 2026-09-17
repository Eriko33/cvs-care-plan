"""Embed a label's chunks and store them in the vector database.

Usage:
    python -m rag.index_chunks rag/labels/privigen.xml "Privigen"
"""
import os
import sys


def index_label(xml_path: str, drug_name: str) -> int:
    from rag.chunk_label import chunk_label
    from rag.embeddings import embed_texts
    from rag.models import DocumentChunk

    chunks = chunk_label(xml_path, drug_name)
    vectors = embed_texts([c.text for c in chunks])

    # Re-indexing a drug replaces its old chunks rather than duplicating them.
    DocumentChunk.objects.filter(drug_name=drug_name).delete()
    DocumentChunk.objects.bulk_create(
        DocumentChunk(
            drug_name=c.drug_name,
            section_name=c.section_name,
            loinc_code=c.loinc_code,
            chunk_index=c.chunk_index,
            text=c.text,
            embedding=vec,
        )
        for c, vec in zip(chunks, vectors)
    )
    return len(chunks)


if __name__ == "__main__":
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()

    xml_path, drug_name = sys.argv[1], sys.argv[2]
    count = index_label(xml_path, drug_name)
    print(f"Indexed {count} chunks for '{drug_name}'")
