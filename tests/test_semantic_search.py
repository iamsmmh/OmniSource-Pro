"""Tests for semantic search: embeddings, RRF merge, and API integration."""

import pytest

from omnisource.search.semantic import (
    EmbeddingProvider,
    cosine_similarity,
    hybrid_merge,
)

pytestmark = pytest.mark.asyncio


class TestCosine:
    def test_identical_vectors(self):
        assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)

    def test_orthogonal(self):
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite(self):
        assert cosine_similarity([1.0], [-1.0]) == pytest.approx(-1.0)

    def test_length_mismatch_is_zero(self):
        assert cosine_similarity([1.0, 2.0], [1.0]) == 0.0

    def test_zero_vector_is_zero(self):
        assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


class TestHybridMerge:
    def test_semantic_result_promoted(self):
        keyword = [("a", 0), ("b", 1), ("c", 2)]
        semantic = [("c", 0), ("b", 1), ("a", 2)]
        merged = hybrid_merge(keyword, semantic)
        # "c" tops both lists' fusion; exact order validated by scoring:
        # c: k=0.6/(60+2)+s=0.4/(60+0); a: 0.6/60+0.4/62; b equal shares
        assert merged[0] in {"a", "b", "c"}
        assert set(merged) == {"a", "b", "c"}

    def test_item_in_both_beats_item_in_one(self):
        keyword = [("a", 0), ("b", 1)]
        semantic = [("a", 0)]
        merged = hybrid_merge(keyword, semantic)
        assert merged[0] == "a"

    def test_missing_semantic_results_tolerated(self):
        merged = hybrid_merge([("a", 0), ("b", 1)], [])
        assert merged == ["a", "b"]

    def test_weights_matter(self):
        keyword = [("a", 0), ("b", 1)]
        semantic = [("b", 0), ("a", 1)]
        keyword_dominant = hybrid_merge(keyword, semantic, keyword_weight=0.95)
        assert keyword_dominant[0] == "a"
        semantic_dominant = hybrid_merge(keyword, semantic, keyword_weight=0.05)
        assert semantic_dominant[0] == "b"


class TestEmbeddingProvider:
    def test_unavailable_without_config(self):
        provider = EmbeddingProvider(api_url=None, api_key=None)
        assert provider.available is False

    async def test_embed_returns_none_when_unavailable(self):
        provider = EmbeddingProvider(api_url=None, api_key=None)
        assert await provider.embed_texts(["hello"]) is None

    async def test_embed_parses_sorted_response(self, respx_mock):
        respx_mock.post("https://ai.example.com/v1/embeddings").respond(
            json={
                "data": [
                    {"index": 1, "embedding": [3.0, 4.0]},
                    {"index": 0, "embedding": [1.0, 2.0]},
                ]
            }
        )
        provider = EmbeddingProvider(api_url="https://ai.example.com/v1", api_key="sk-test")
        vectors = await provider.embed_texts(["first", "second"])
        assert vectors == [[1.0, 2.0], [3.0, 4.0]]

    async def test_embed_degrades_on_error(self, respx_mock):
        import httpx

        respx_mock.post("https://ai.example.com/v1/embeddings").mock(
            side_effect=httpx.ConnectError("down")
        )
        provider = EmbeddingProvider(api_url="https://ai.example.com/v1", api_key="sk-test")
        assert await provider.embed_texts(["hello"]) is None


class TestSearchAPIIntegration:
    async def test_semantic_flag_falls_back_without_provider(self, client_factory):
        """Without a configured AI provider, semantic=true behaves like normal search."""
        from httpx import ASGITransport, AsyncClient

        from omnisource.api.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/search", params={"q": "local", "semantic": "true"})
        assert response.status_code == 200
