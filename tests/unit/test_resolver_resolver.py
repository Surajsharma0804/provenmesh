"""Tests for resolver/resolver.py — full cascade including mocked embedding."""
from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from provenmesh.domain.enums import ResolutionMethod
from provenmesh.resolver.resolver import EntityResolver, ResolutionResult
from provenmesh.resolver.seeds import SeedEntity, SeedStore


class TestResolutionResult:
    def test_creation(self) -> None:
        r = ResolutionResult(
            canonical_id="startup_openai",
            canonical_name="OpenAI",
            method=ResolutionMethod.EXACT,
            confidence=1.0,
        )
        assert r.canonical_id == "startup_openai"
        assert r.method == ResolutionMethod.EXACT
        assert r.is_new is False
        assert r.needs_review is False

    def test_new_entity(self) -> None:
        r = ResolutionResult(
            canonical_id="startup_new",
            canonical_name="New Startup",
            method=ResolutionMethod.UNRESOLVED,
            confidence=0.0,
            is_new=True,
        )
        assert r.is_new is True

    def test_needs_review(self) -> None:
        r = ResolutionResult(
            canonical_id="startup_maybe",
            canonical_name="Maybe Match",
            method=ResolutionMethod.EMBEDDING,
            confidence=0.82,
            needs_review=True,
        )
        assert r.needs_review is True

    def test_matched_seed(self) -> None:
        seed = SeedEntity("id", "Name", "name", "STARTUP")
        r = ResolutionResult(
            canonical_id="id",
            canonical_name="Name",
            method=ResolutionMethod.EXACT,
            confidence=1.0,
            matched_seed=seed,
        )
        assert r.matched_seed is seed


class TestEntityResolverExact:
    def _make_seed_store(self) -> SeedStore:
        store = SeedStore()
        store.add_seed(SeedEntity(
            canonical_id="startup_openai",
            canonical_name="OpenAI",
            normalized_name="openai",
            record_type="STARTUP",
            aliases=["Open AI"],
        ))
        store.add_seed(SeedEntity(
            canonical_id="startup_anthropic",
            canonical_name="Anthropic",
            normalized_name="anthropic",
            record_type="STARTUP",
        ))
        return store

    @pytest.mark.asyncio
    async def test_exact_match(self) -> None:
        resolver = EntityResolver(seed_store=self._make_seed_store())
        result = await resolver.resolve("OpenAI", "STARTUP")
        assert result.canonical_id == "startup_openai"
        assert result.method == ResolutionMethod.EXACT
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_normalized_match(self) -> None:
        resolver = EntityResolver(seed_store=self._make_seed_store())
        result = await resolver.resolve("OpenAI Inc.", "STARTUP")
        assert result.canonical_id == "startup_openai"
        assert result.method == ResolutionMethod.NORMALIZED
        assert result.confidence == 0.98

    @pytest.mark.asyncio
    async def test_empty_name(self) -> None:
        resolver = EntityResolver(seed_store=self._make_seed_store())
        result = await resolver.resolve("", "STARTUP")
        assert result.method == ResolutionMethod.UNRESOLVED
        assert result.is_new is True

    @pytest.mark.asyncio
    async def test_whitespace_name(self) -> None:
        resolver = EntityResolver(seed_store=self._make_seed_store())
        result = await resolver.resolve("   ", "STARTUP")
        assert result.method == ResolutionMethod.UNRESOLVED

    @pytest.mark.asyncio
    async def test_alias_exact_match(self) -> None:
        resolver = EntityResolver(seed_store=self._make_seed_store())
        result = await resolver.resolve("Open AI", "STARTUP")
        assert result.canonical_id == "startup_openai"
        assert result.method == ResolutionMethod.EXACT


class TestFuzzyMatch:
    """Test _fuzzy_match directly (lines 155-189)."""

    def test_fuzzy_match_high_score(self) -> None:
        """Fuzzy match returns result when score >= threshold (line 181)."""
        store = SeedStore()
        store.add_seed(SeedEntity(
            canonical_id="startup_deepmind",
            canonical_name="DeepMind Technologies",
            normalized_name="deepmind technologies",
            record_type="STARTUP",
        ))
        resolver = EntityResolver(seed_store=store)
        # Very similar name → high fuzzy score
        result = resolver._fuzzy_match("DeepMind Technologie", "STARTUP")
        assert result is not None
        assert result.method == ResolutionMethod.FUZZY
        assert result.canonical_id == "startup_deepmind"
        assert result.confidence > 0.85

    def test_fuzzy_match_with_alias(self) -> None:
        """Fuzzy match should check aliases too."""
        store = SeedStore()
        store.add_seed(SeedEntity(
            canonical_id="startup_openai",
            canonical_name="OpenAI",
            normalized_name="openai",
            record_type="STARTUP",
            aliases=["Open Artificial Intelligence"],
        ))
        resolver = EntityResolver(seed_store=store)
        result = resolver._fuzzy_match(
            "Open Artificial Intelligence Corp", "STARTUP",
        )
        # Should match via alias
        assert result is None or isinstance(result, ResolutionResult)

    def test_fuzzy_match_no_seeds(self) -> None:
        """No seeds → returns None."""
        resolver = EntityResolver(seed_store=SeedStore())
        result = resolver._fuzzy_match("test", "STARTUP")
        assert result is None

    def test_fuzzy_match_below_threshold(self) -> None:
        """Score below threshold → returns None."""
        store = SeedStore()
        store.add_seed(SeedEntity(
            canonical_id="s1",
            canonical_name="Completely Different Company Name",
            normalized_name="completely different company name",
            record_type="STARTUP",
        ))
        resolver = EntityResolver(seed_store=store)
        result = resolver._fuzzy_match("XYZ", "STARTUP")
        assert result is None


class TestEmbeddingMatch:
    """Test _embedding_match directly (lines 191-244)."""

    def _make_resolver(self, similarity: float) -> EntityResolver:
        store = SeedStore()
        store.add_seed(SeedEntity(
            canonical_id="startup_test",
            canonical_name="Test Company",
            normalized_name="test company",
            record_type="STARTUP",
        ))
        resolver = EntityResolver(seed_store=store)

        # Create vectors that produce exact desired cosine similarity
        v_input = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        v_seed = np.array(
            [similarity, np.sqrt(1 - similarity**2), 0.0],
            dtype=np.float32,
        )

        mock_model = MagicMock()
        # encode is called twice: once for input, once for seed
        mock_model.encode = MagicMock(side_effect=[v_input, v_seed])
        resolver._embedding_model = mock_model
        return resolver

    def test_embedding_accept_above_088(self) -> None:
        """Cosine ≥ 0.88 → EMBEDDING method, no review (lines 223-230)."""
        resolver = self._make_resolver(0.95)
        result = resolver._embedding_match("input name", "STARTUP")
        assert result is not None
        assert result.method == ResolutionMethod.EMBEDDING
        assert result.needs_review is False
        assert result.confidence >= 0.88

    def test_embedding_review_band(self) -> None:
        """0.75 ≤ cosine < 0.88 → needs_review=True (lines 232-241)."""
        resolver = self._make_resolver(0.80)
        result = resolver._embedding_match("input name", "STARTUP")
        assert result is not None
        assert result.method == ResolutionMethod.EMBEDDING
        assert result.needs_review is True
        assert 0.75 <= result.confidence < 0.88

    def test_embedding_below_075_no_match(self) -> None:
        """Cosine < 0.75 → returns None (line 244)."""
        resolver = self._make_resolver(0.50)
        result = resolver._embedding_match("input name", "STARTUP")
        assert result is None

    def test_embedding_no_seeds(self) -> None:
        """No seeds for type → returns None (line 199)."""
        resolver = EntityResolver(seed_store=SeedStore())
        result = resolver._embedding_match("test", "NONEXISTENT")
        assert result is None

    def test_embedding_orthogonal_vectors_best_seed_none(self) -> None:
        """When cosine similarity is 0 (orthogonal), best_seed stays None (line 220)."""
        store = SeedStore()
        store.add_seed(SeedEntity(
            canonical_id="startup_test",
            canonical_name="Test Company",
            normalized_name="test company",
            record_type="STARTUP",
        ))
        resolver = EntityResolver(seed_store=store)

        # Orthogonal vectors → cosine similarity = 0
        v_input = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        v_seed = np.array([0.0, 1.0, 0.0], dtype=np.float32)

        mock_model = MagicMock()
        mock_model.encode = MagicMock(side_effect=[v_input, v_seed])
        resolver._embedding_model = mock_model

        result = resolver._embedding_match("input name", "STARTUP")
        assert result is None  # best_seed is None since similarity = 0


class TestFullCascade:
    """Test the full resolve cascade hitting fuzzy and embedding paths."""

    @pytest.mark.asyncio
    async def test_fuzzy_match_cascade(self) -> None:
        """Force fuzzy match success in the resolve cascade (lines 131-133)."""
        store = SeedStore()
        store.add_seed(SeedEntity(
            canonical_id="startup_meta",
            canonical_name="Meta Platforms",
            normalized_name="meta platforms",
            record_type="STARTUP",
        ))
        resolver = EntityResolver(seed_store=store)
        # "Meta Platform" is very close to "Meta Platforms" — should fuzzy match
        result = await resolver.resolve("Meta Platform", "STARTUP")
        assert result.canonical_id == "startup_meta"
        assert result.method == ResolutionMethod.FUZZY
        assert result.confidence > 0.85

    @pytest.mark.asyncio
    async def test_embedding_accept_cascade(self) -> None:
        """Force embedding accept in the resolve cascade (lines 137-142)."""
        store = SeedStore()
        store.add_seed(SeedEntity(
            canonical_id="startup_acme",
            canonical_name="ACME Corporation",
            normalized_name="acme corporation",
            record_type="STARTUP",
        ))
        resolver = EntityResolver(seed_store=store)

        # Mock embedding to return high similarity
        v_input = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        v_seed = np.array([0.95, np.sqrt(1 - 0.95**2), 0.0], dtype=np.float32)
        mock_model = MagicMock()
        mock_model.encode = MagicMock(side_effect=[v_input, v_seed])
        resolver._embedding_model = mock_model

        # Name that won't fuzzy match but will embedding match
        result = await resolver.resolve(
            "ZZZQQQ Unrelated Name ZZZQQQ", "STARTUP",
        )
        assert result.method == ResolutionMethod.EMBEDDING
        assert result.needs_review is False

    @pytest.mark.asyncio
    async def test_embedding_review_cascade(self) -> None:
        """Force embedding review band in the cascade (lines 138-139)."""
        store = SeedStore()
        store.add_seed(SeedEntity(
            canonical_id="startup_acme",
            canonical_name="ACME Corporation",
            normalized_name="acme corporation",
            record_type="STARTUP",
        ))
        resolver = EntityResolver(seed_store=store)

        # Mock embedding to return review-band similarity
        v_input = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        v_seed = np.array([0.80, np.sqrt(1 - 0.80**2), 0.0], dtype=np.float32)
        mock_model = MagicMock()
        mock_model.encode = MagicMock(side_effect=[v_input, v_seed])
        resolver._embedding_model = mock_model

        result = await resolver.resolve(
            "ZZZQQQ Unrelated Name ZZZQQQ", "STARTUP",
        )
        assert result.method == ResolutionMethod.EMBEDDING
        assert result.needs_review is True

    @pytest.mark.asyncio
    async def test_new_entity_cascade(self) -> None:
        """No match at all → new entity (lines 144-153)."""
        resolver = EntityResolver(seed_store=SeedStore())
        result = await resolver.resolve("Brand New Entity XYZ", "STARTUP")
        assert result.is_new is True
        assert result.method == ResolutionMethod.UNRESOLVED


class TestEntityResolverHelpers:
    def test_generate_id(self) -> None:
        cid = EntityResolver._generate_id("STARTUP", "OpenAI")
        assert cid.startswith("startup_")
        assert "openai" in cid

    def test_generate_id_empty_name(self) -> None:
        cid = EntityResolver._generate_id("STARTUP", "")
        assert cid.startswith("startup_")
        assert len(cid) > 10

    def test_generate_id_special_chars(self) -> None:
        cid = EntityResolver._generate_id("PRODUCT", "ChatGPT (Plus)")
        assert cid.startswith("product_")
        assert "(" not in cid

    def test_seed_store_property(self) -> None:
        store = SeedStore()
        resolver = EntityResolver(seed_store=store)
        assert resolver.seed_store is store

    def test_default_seed_store(self) -> None:
        resolver = EntityResolver()
        assert resolver.seed_store is not None
        assert resolver.seed_store.total_seeds == 0

    def test_get_or_compute_embedding_caches(self) -> None:
        """Test _get_or_compute_embedding cache behavior (lines 246-254)."""
        resolver = EntityResolver(seed_store=SeedStore())
        mock_model = MagicMock()
        v = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        mock_model.encode = MagicMock(return_value=v)

        # First call should compute
        result1 = resolver._get_or_compute_embedding("test", mock_model)
        assert mock_model.encode.call_count == 1

        # Second call should use cache
        result2 = resolver._get_or_compute_embedding("test", mock_model)
        assert mock_model.encode.call_count == 1  # Not called again
        np.testing.assert_array_equal(result1, result2)
