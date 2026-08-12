"""Entity name normalization — pre-resolution text cleanup (v2 §23).

Normalizes entity names before matching to increase resolution accuracy.
"""

from __future__ import annotations

import re
import unicodedata

# Legal suffixes to strip
LEGAL_SUFFIXES = re.compile(
    r"\b(?:inc\.?|ltd\.?|corp\.?|llc\.?|plc\.?|gmbh|co\.?|limited|corporation|company|"
    r"technologies|labs?|ai|group|holdings?|ventures?|studios?|software|systems|platform|"
    r"networks?|solutions|services|international|global|digital)\b",
    re.IGNORECASE,
)

# Parenthetical info to strip: "Company (formerly X)"
PARENS = re.compile(r"\s*\(.*?\)\s*")

# Common joiners that should be collapsed
JOINERS = re.compile(r"[-–—_]+")


def normalize_entity_name(name: str) -> str:
    """Full normalization pipeline for entity names.

    Pipeline:
        1. Unicode NFKD normalization (decompose accents)
        2. Lowercase
        3. Strip parenthetical info
        4. Strip legal suffixes
        5. Collapse joiners to spaces
        6. Collapse whitespace
        7. Strip edge punctuation
    """
    if not name:
        return ""

    # Unicode normalize
    name = unicodedata.normalize("NFKD", name)

    # Lowercase
    name = name.lower().strip()

    # Strip parenthetical info
    name = PARENS.sub(" ", name)

    # Strip legal suffixes
    name = LEGAL_SUFFIXES.sub("", name)

    # Collapse joiners
    name = JOINERS.sub(" ", name)

    # Collapse whitespace
    name = re.sub(r"\s+", " ", name).strip()

    # Strip edge punctuation
    name = name.strip(".,;:!?-—–'\"")

    return name


def generate_slug(name: str) -> str:
    """Generate a URL-safe slug from an entity name.

    Used for deterministic canonical_id generation.
    """
    normalized = normalize_entity_name(name)
    # Replace spaces with hyphens
    slug = re.sub(r"\s+", "-", normalized)
    # Remove non-alphanumeric (except hyphens)
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    # Collapse multiple hyphens
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "unknown"


def generate_canonical_id(name: str, record_type: str) -> str:
    """Generate a deterministic canonical ID.

    Format: {type_prefix}_{slug}
    Example: startup_openai, product_chatgpt
    """
    type_prefix = record_type.lower().replace("_", "-")
    if type_prefix == "news-signal":
        type_prefix = "news"
    slug = generate_slug(name)
    return f"{type_prefix}_{slug}"


def extract_acronym(name: str) -> str | None:
    """Extract an acronym if the name looks like one (all caps, ≤6 chars)."""
    clean = name.strip()
    if len(clean) <= 6 and clean.isupper() and clean.isalpha():
        return clean
    return None
