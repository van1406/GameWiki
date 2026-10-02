"""
embeddings.py
-------------
Sentence-Transformers based embeddings, exposed through a small class that
implements the LangChain `Embeddings` interface (embed_documents / embed_query).

Notes:
  * The model is downloaded on first use and cached by sentence-transformers.
  * Vectors are L2-normalized, so similarity can be measured with plain
    cosine similarity (see rag_pipeline.py).
  * The model name is configurable with the EMBEDDING_MODEL env variable.
"""

from __future__ import annotations

import os
from typing import List

from langchain_core.embeddings import Embeddings

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# One shared model instance (loading a transformer is expensive).
_cache: dict[str, "SentenceTransformerEmbeddings"] = {}


class SentenceTransformerEmbeddings(Embeddings):
    """LangChain-compatible embedding wrapper around sentence-transformers."""

    def __init__(self, model_name: str | None = None, cache_folder: str | None = None):
        self.model_name = model_name or os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL)
        # Lazy import so simply importing this module stays cheap.
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(
            self.model_name,
            cache_folder=cache_folder or os.getenv("EMBEDDING_MODEL_CACHE") or None,
        )

    def _encode(self, texts: List[str]) -> List[List[float]]:
        # normalize_embeddings=True -> every vector has length 1, which makes
        # cosine similarity computable from the L2 distance FAISS returns.
        vectors = self._model.encode(
            list(texts), normalize_embeddings=True, show_progress_bar=False
        )
        return vectors.tolist()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of chunks for indexing."""
        return self._encode(texts)

    def embed_query(self, text: str) -> List[float]:
        """Embed the user's question for retrieval."""
        return self._encode([text])[0]


def get_embeddings() -> SentenceTransformerEmbeddings:
    """Return a shared embeddings instance for the configured model."""
    model_name = os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL)
    if model_name not in _cache:
        _cache[model_name] = SentenceTransformerEmbeddings(model_name)
    return _cache[model_name]
