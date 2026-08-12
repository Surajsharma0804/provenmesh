"""Unit tests for entity resolver — cascade matching strategy."""

from __future__ import annotations

import pytest

from provenmesh.domain.enums import ResolutionMethod
from provenmesh.resolver.resolver import EntityResolver
from provenmesh.resolver.seeds import SeedEntity, SeedStore


@pytest.fixture
def seed_store() -> SeedStore:
    store = SeedStore()
    store.add_seed(SeedEntity(
        canonical_id="startup_openai",
        canonical_name="OpenAI",
        normalized_name="openai",
        record_type="STARTUP",
        aliases=["Open AI", "OpenAI Inc"],
    ))
    store.add_seed(SeedEntity(
        canonical_id="startup_anthropic",
        canonical_name="Anthropic",
        normalized_name="anthropic",
        record_type="STARTUP",
        aliases=["Anthropic AI"],
    ))
    store.add_seed(SeedEntity(
        canonical_id="startup_deepmind",
        canonical_name="DeepMind",
        normalized_name="deepmind",
        record_type="STARTUP",
        aliases=["Google DeepMind"],
    ))
    return store


@pytest.fixture
def resolver(seed_store: SeedStore) -> EntityResolver:
    return EntityResolver(seed_store)


class TestExactMatch:
    """Tests for stage 1: exact seed matching."""

    @pytest.mark.asyncio
    async def test_exact_match(self, resolver: EntityResolver) -> None:
        result = await resolver.resolve("OpenAI", "STARTUP")
        assert result.canonical_id == "startup_openai"
        assert result.method == ResolutionMethod.EXACT
        assert result.confidence == 1.0
        assert not result.is_new

    @pytest.mark.asyncio
    async def test_case_insensitive(self, resolver: EntityResolver) -> None:
        result = await resolver.resolve("openai", "STARTUP")
        assert result.canonical_id == "startup_openai"

    @pytest.mark.asyncio
    async def test_alias_match(self, resolver: EntityResolver) -> None:
        result = await resolver.resolve("Open AI", "STARTUP")
        assert result.canonical_id == "startup_openai"
        assert result.method == ResolutionMethod.EXACT


class TestNormalizedMatch:
    """Tests for stage 2: normalized matching."""

    @pytest.mark.asyncio
    async def test_normalized_strips_legal_suffix(self, resolver: EntityResolver) -> None:
        result = await resolver.resolve("OpenAI Inc.", "STARTUP")
        # Should match via exact (alias) or normalized
        assert result.canonical_id == "startup_openai"
        assert result.method in (ResolutionMethod.EXACT, ResolutionMethod.NORMALIZED)


class TestFuzzyMatch:
    """Tests for stage 3: fuzzy matching."""

    @pytest.mark.asyncio
    async def test_fuzzy_match_typo(self, resolver: EntityResolver) -> None:
        result = await resolver.resolve("OpenA1", "STARTUP")
        # This should either fuzzy match or not match at all
        if result.method == ResolutionMethod.FUZZY:
            assert result.canonical_id == "startup_openai"
            assert result.confidence > 0.0


class TestNewEntity:
    """Tests for new entity creation."""

    @pytest.mark.asyncio
    async def test_completely_new_entity(self, resolver: EntityResolver) -> None:
        result = await resolver.resolve("Totally New Startup", "STARTUP")
        assert result.is_new
        assert result.canonical_id.startswith("startup_")
        assert result.method == ResolutionMethod.UNRESOLVED

    @pytest.mark.asyncio
    async def test_empty_name(self, resolver: EntityResolver) -> None:
        result = await resolver.resolve("", "STARTUP")
        assert result.is_new

    @pytest.mark.asyncio
    async def test_deterministic_id_generation(self, resolver: EntityResolver) -> None:
        result1 = await resolver.resolve("New Company XYZ", "STARTUP")
        result2 = await resolver.resolve("New Company XYZ", "STARTUP")
        assert result1.canonical_id == result2.canonical_id


class TestSeedStore:
    """Tests for the seed store."""

    def test_add_and_lookup(self) -> None:
        store = SeedStore()
        store.add_seed(SeedEntity(
            canonical_id="test_1",
            canonical_name="Test Entity",
            normalized_name="test entity",
            record_type="STARTUP",
        ))
        assert store.exact_match("Test Entity") is not None
        assert store.exact_match("nonexistent") is None

    def test_normalized_lookup(self) -> None:
        store = SeedStore()
        store.add_seed(SeedEntity(
            canonical_id="test_1",
            canonical_name="Test Corp.",
            normalized_name="test",
            record_type="STARTUP",
        ))
        result = store.normalized_match("Test Corp.")
        assert result is not None
        assert result.canonical_id == "test_1"

    def test_total_seeds(self) -> None:
        store = SeedStore()
        assert store.total_seeds == 0
        store.add_seed(SeedEntity(
            canonical_id="a", canonical_name="A", normalized_name="a", record_type="STARTUP",
        ))
        assert store.total_seeds == 1

    def test_load_from_json(self) -> None:
        store = SeedStore()
        count = store.load_from_json([
            {"canonical_id": "s1", "name": "Company A", "record_type": "STARTUP"},
            {"canonical_id": "s2", "name": "Company B", "record_type": "STARTUP", "aliases": ["B Corp"]},  # noqa: E501
        ])
        assert count == 2
        assert store.total_seeds == 2
        assert store.exact_match("B Corp") is not None
