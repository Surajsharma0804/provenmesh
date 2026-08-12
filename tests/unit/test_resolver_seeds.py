"""Tests for resolver/seeds.py — SeedStore exact/normalized matching."""
from __future__ import annotations

from provenmesh.resolver.seeds import SeedEntity, SeedStore


class TestSeedEntity:
    def test_creation(self) -> None:
        s = SeedEntity(
            canonical_id="startup_openai",
            canonical_name="OpenAI",
            normalized_name="openai",
            record_type="STARTUP",
        )
        assert s.canonical_id == "startup_openai"
        assert s.aliases == []
        assert s.source_count == 0


class TestSeedStore:
    def test_add_and_exact_match(self) -> None:
        store = SeedStore()
        seed = SeedEntity(
            canonical_id="startup_openai",
            canonical_name="OpenAI",
            normalized_name="openai",
            record_type="STARTUP",
        )
        store.add_seed(seed)
        assert store.exact_match("OpenAI") is seed
        assert store.exact_match("openai") is seed

    def test_normalized_match(self) -> None:
        store = SeedStore()
        seed = SeedEntity(
            canonical_id="startup_openai",
            canonical_name="OpenAI",
            normalized_name="openai",
            record_type="STARTUP",
        )
        store.add_seed(seed)
        match = store.normalized_match("OpenAI Inc.")
        assert match is seed

    def test_alias_matching(self) -> None:
        store = SeedStore()
        seed = SeedEntity(
            canonical_id="startup_openai",
            canonical_name="OpenAI",
            normalized_name="openai",
            record_type="STARTUP",
            aliases=["Open AI", "OpenAI Inc"],
        )
        store.add_seed(seed)
        assert store.exact_match("Open AI") is seed
        assert store.exact_match("openai inc") is seed

    def test_get_by_id(self) -> None:
        store = SeedStore()
        seed = SeedEntity(
            canonical_id="startup_openai",
            canonical_name="OpenAI",
            normalized_name="openai",
            record_type="STARTUP",
        )
        store.add_seed(seed)
        assert store.get_by_id("startup_openai") is seed
        assert store.get_by_id("nonexistent") is None

    def test_get_seeds_for_type(self) -> None:
        store = SeedStore()
        seed = SeedEntity(
            canonical_id="startup_openai",
            canonical_name="OpenAI",
            normalized_name="openai",
            record_type="STARTUP",
        )
        store.add_seed(seed)
        assert len(store.get_seeds_for_type("STARTUP")) == 1
        assert store.get_seeds_for_type("PRODUCT") == []

    def test_total_seeds(self) -> None:
        store = SeedStore()
        assert store.total_seeds == 0
        store.add_seed(SeedEntity("a", "A", "a", "STARTUP"))
        store.add_seed(SeedEntity("b", "B", "b", "STARTUP"))
        assert store.total_seeds == 2

    def test_no_match(self) -> None:
        store = SeedStore()
        assert store.exact_match("Nothing") is None
        assert store.normalized_match("Nothing") is None

    def test_promote_to_seed(self) -> None:
        store = SeedStore()
        seed = store.promote_to_seed(
            canonical_id="startup_test",
            name="Test Startup",
            record_type="STARTUP",
            source_count=5,
        )
        assert seed.canonical_id == "startup_test"
        assert seed.source_count == 5
        assert store.get_by_id("startup_test") is seed

    def test_load_from_json(self) -> None:
        store = SeedStore()
        json_data = [
            {"canonical_id": "s1", "name": "OpenAI", "record_type": "STARTUP"},
            {"canonical_id": "s2", "name": "Anthropic", "aliases": ["Anthro"]},
        ]
        count = store.load_from_json(json_data)
        assert count == 2
        assert store.total_seeds == 2
        assert store.exact_match("OpenAI") is not None
        assert store.exact_match("Anthro") is not None
