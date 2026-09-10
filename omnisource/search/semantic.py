"""Semantic (embedding-based) search with hybrid re-ranking.

Two cooperating pieces:

1. ``EmbeddingProvider`` — an optional OpenAI-compatible embeddings client
   configured through ``AI_API_URL``/``AI_API_KEY`` (+ ``AI_EMBEDDING_MODEL``).
   When unconfigured, the provider reports ``available=False`` and every
   consumer falls back to plain keyword search.

2. ``hybrid_merge`` — a reciprocal-rank-fusion merge that combines keyword
   results with embedding-similarity results. RRF needs no score calibration
   between the two systems, which keeps the merge stable across models.

Embeddings are stored in the ``app_embeddings`` table (JSON column). This is
intentionally simple and portable; production deployments with >100k apps
should swap the storage layer for pgvector.
"""

import math
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnisource.config.logging import get_logger
from omnisource.config.settings import get_settings
from omnisource.core.models.application import Application
from omnisource.core.models.embedding import AppEmbedding

logger = get_logger(__name__)


class EmbeddingProvider:
    """OpenAI-compatible embeddings client; degrades gracefully when unset."""

    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        settings = get_settings()
        self.api_url = (api_url or settings.ai.AI_API_URL or "").rstrip("/")
        self.api_key = api_key or settings.ai.AI_API_KEY
        self.model = model or settings.ai.AI_EMBEDDING_MODEL or "text-embedding-3-small"

    @property
    def available(self) -> bool:
        return bool(self.api_url and self.api_key)

    async def embed_texts(self, texts: list[str]) -> list[list[float]] | None:
        """Embed a batch of texts; returns None when unavailable/failed."""
        if not self.available or not texts:
            return None
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.api_url}/embeddings",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={"model": self.model, "input": texts},
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Embedding request failed: %s", exc)
            return None
        try:
            sorted_items = sorted(data["data"], key=lambda item: item["index"])
            return [item["embedding"] for item in sorted_items]
        except (KeyError, TypeError):
            logger.warning("Malformed embedding response")
            return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _rrf_score(rank: int, k: int = 60) -> float:
    return 1.0 / (k + rank)


def hybrid_merge(
    keyword_results: list[tuple[str, int]],
    semantic_results: list[tuple[str, int]],
    keyword_weight: float = 0.6,
    semantic_weight: float = 0.4,
    k: int = 60,
) -> list[str]:
    """Reciprocal-rank-fusion of keyword and semantic result lists.

    Args:
        keyword_results: Ordered ``(app_id, rank)`` pairs from keyword search.
        semantic_results: Ordered ``(app_id, rank)`` pairs from similarity.
        keyword_weight / semantic_weight: Relative contributions.
        k: RRF smoothing constant.

    Returns app_ids ordered by fused score (ties keep keyword order).
    """
    scores: dict[str, float] = {}
    for app_id, rank in keyword_results:
        scores[app_id] = scores.get(app_id, 0.0) + keyword_weight * _rrf_score(rank, k)
    for app_id, rank in semantic_results:
        scores[app_id] = scores.get(app_id, 0.0) + semantic_weight * _rrf_score(rank, k)
    # stable sort: dict preserves first-seen order for ties
    return sorted(scores, key=lambda app_id: scores[app_id], reverse=True)


@dataclass
class SemanticSearchResult:
    """The merged output of a hybrid search."""

    ordered_app_ids: list[str]
    used_semantic: bool


async def app_embedding_text(app: Application) -> str:
    """Build the canonical text used to embed an application."""
    parts = [app.name or "", app.short_description or "", app.long_description or ""]
    parts.extend(tag.slug for tag in (app.tags or []))
    return " ".join(p for p in parts if p).strip()


async def get_stored_embeddings(
    session: AsyncSession, application_ids: list[str]
) -> dict[str, list[float]]:
    """Load stored embeddings for the given app ids (current model)."""
    provider = EmbeddingProvider()
    if not application_ids:
        return {}
    rows = await session.execute(
        select(AppEmbedding).where(
            AppEmbedding.application_id.in_(application_ids),
            AppEmbedding.model == provider.model,
        )
    )
    return {str(row.application_id): list(row.embedding) for row in rows.scalars()}


__all__ = [
    "AppEmbedding",
    "EmbeddingProvider",
    "SemanticSearchResult",
    "app_embedding_text",
    "cosine_similarity",
    "get_stored_embeddings",
    "hybrid_merge",
]
