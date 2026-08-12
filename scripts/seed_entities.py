"""Seed entities loader — populate seed store from JSON for deterministic matching.

Usage:
    python scripts/seed_entities.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from provenmesh.graph.models import EntityRecord
from provenmesh.graph.repository import EntityRepository
from provenmesh.resolver.seeds import SeedEntity, SeedStore
from provenmesh.storage.transactions import unit_of_work


SEED_DATA = [
    # AI Companies — Tier 1
    {"canonical_id": "startup_openai", "name": "OpenAI", "record_type": "STARTUP",
     "aliases": ["Open AI", "OpenAI Inc", "OpenAI LP"]},
    {"canonical_id": "startup_anthropic", "name": "Anthropic", "record_type": "STARTUP",
     "aliases": ["Anthropic AI", "Anthropic PBC"]},
    {"canonical_id": "startup_deepmind", "name": "DeepMind", "record_type": "STARTUP",
     "aliases": ["Google DeepMind", "DeepMind Technologies"]},
    {"canonical_id": "startup_meta-ai", "name": "Meta AI", "record_type": "STARTUP",
     "aliases": ["FAIR", "Facebook AI Research"]},
    {"canonical_id": "startup_mistral", "name": "Mistral AI", "record_type": "STARTUP",
     "aliases": ["Mistral"]},
    {"canonical_id": "startup_cohere", "name": "Cohere", "record_type": "STARTUP",
     "aliases": ["Cohere AI"]},
    {"canonical_id": "startup_stability-ai", "name": "Stability AI", "record_type": "STARTUP",
     "aliases": ["Stability"]},
    {"canonical_id": "startup_hugging-face", "name": "Hugging Face", "record_type": "STARTUP",
     "aliases": ["HuggingFace", "🤗"]},
    {"canonical_id": "startup_scale-ai", "name": "Scale AI", "record_type": "STARTUP",
     "aliases": ["Scale"]},
    {"canonical_id": "startup_perplexity", "name": "Perplexity AI", "record_type": "STARTUP",
     "aliases": ["Perplexity"]},
    {"canonical_id": "startup_runway", "name": "Runway", "record_type": "STARTUP",
     "aliases": ["Runway ML", "RunwayML"]},
    {"canonical_id": "startup_midjourney", "name": "Midjourney", "record_type": "STARTUP",
     "aliases": ["MidJourney"]},
    {"canonical_id": "startup_inflection-ai", "name": "Inflection AI", "record_type": "STARTUP",
     "aliases": ["Inflection"]},
    {"canonical_id": "startup_xai", "name": "xAI", "record_type": "STARTUP",
     "aliases": ["X.AI"]},
    {"canonical_id": "startup_databricks", "name": "Databricks", "record_type": "STARTUP",
     "aliases": ["Databricks Inc"]},

    # Products — Tier 1
    {"canonical_id": "product_chatgpt", "name": "ChatGPT", "record_type": "PRODUCT",
     "aliases": ["Chat GPT", "GPT-4", "GPT-4o"]},
    {"canonical_id": "product_claude", "name": "Claude", "record_type": "PRODUCT",
     "aliases": ["Claude AI", "Claude 3", "Claude 3.5 Sonnet"]},
    {"canonical_id": "product_gemini", "name": "Gemini", "record_type": "PRODUCT",
     "aliases": ["Google Gemini", "Gemini Pro", "Gemini Flash"]},
    {"canonical_id": "product_copilot", "name": "GitHub Copilot", "record_type": "PRODUCT",
     "aliases": ["Copilot", "GH Copilot"]},
    {"canonical_id": "product_dall-e", "name": "DALL-E", "record_type": "PRODUCT",
     "aliases": ["DALL·E", "DALL-E 3"]},
    {"canonical_id": "product_stable-diffusion", "name": "Stable Diffusion", "record_type": "PRODUCT",
     "aliases": ["SD", "SDXL", "Stable Diffusion XL"]},
]


async def seed_database() -> None:
    """Load seed entities into the database and create the seed store."""
    store = SeedStore()
    count = store.load_from_json(SEED_DATA)
    print(f"Loaded {count} seed entities into memory store")

    # Also persist to database for durability
    async with unit_of_work() as session:
        repo = EntityRepository(session)
        for seed_data in SEED_DATA:
            entity = EntityRecord(
                canonical_id=seed_data["canonical_id"],
                record_type=seed_data["record_type"],
                entity_name=seed_data["name"],
                normalized_name=seed_data["name"].lower(),
                content={"source": "seed"},
                resolution_method="seed",
                resolution_confidence=1.0,
                is_seed=True,
                verification_status="grounded",
                schema_valid=True,
            )
            await repo.upsert(entity)

    print(f"Persisted {len(SEED_DATA)} seed entities to database")


if __name__ == "__main__":
    asyncio.run(seed_database())
