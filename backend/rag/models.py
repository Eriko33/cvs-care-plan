from django.db import models
from pgvector.django import HnswIndex, VectorField

from .embeddings import EMBEDDING_DIM


class DocumentChunk(models.Model):
    drug_name = models.CharField(max_length=255)
    section_name = models.CharField(max_length=255)
    loinc_code = models.CharField(max_length=50, blank=True, null=True)
    chunk_index = models.IntegerField()
    text = models.TextField()
    embedding = VectorField(dimensions=EMBEDDING_DIM)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            HnswIndex(
                name="document_chunk_embedding_hnsw",
                fields=["embedding"],
                opclasses=["vector_cosine_ops"],
                m=16,
                ef_construction=64,
            )
        ]

    def __str__(self):
        return f"{self.drug_name} - {self.section_name} [{self.chunk_index}]"
