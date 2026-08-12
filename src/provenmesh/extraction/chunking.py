"""Semantic chunking — 413 prevention (PDF §5.2, v2 §16-17).

Pipeline: HTML → Readability extraction → paragraph boundaries →
token counting → 70% context cap → LLM.

Removes 60-80% dead weight (nav, ads, scripts) before chunking.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TextChunk:
    """A single semantic chunk of text ready for LLM extraction."""

    text: str
    token_count: int
    chunk_index: int
    total_chunks: int
    has_structured_markup: bool = False  # Tables, definition lists (for merge priority)
    start_offset: int = 0
    end_offset: int = 0


def estimate_tokens(text: str) -> int:
    """Estimate token count (rough: ~4 chars per token for English).

    For production, use tiktoken. This is a fast approximation
    for chunking decisions.
    """
    return max(1, len(text) // 4)


def extract_main_content(html: str) -> str:
    """Extract main content from HTML, removing navigation, ads, scripts.

    Removes 60-80% dead weight (PDF §5.2).
    """
    try:
        from readability import Document
        doc = Document(html)
        cleaned = doc.summary()
    except Exception:
        cleaned = html

    soup = BeautifulSoup(cleaned, "lxml")

    # Remove remaining noise
    for tag in soup.find_all(["script", "style", "nav", "footer", "header",
                               "aside", "iframe", "noscript", "form"]):
        tag.decompose()

    # Remove hidden elements
    for tag in soup.find_all(attrs={"style": re.compile(r"display:\s*none", re.I)}):
        tag.decompose()

    # Get text with preserved structure
    text = soup.get_text(separator="\n", strip=True)

    # Normalize whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)

    return text.strip()


def has_structured_content(html_chunk: str) -> bool:
    """Check if a chunk contains structured markup (tables, lists).

    Used for merge conflict resolution (v2 §17):
    structured markup > explicit prose > weak inference.
    """
    soup = BeautifulSoup(html_chunk, "lxml")
    return bool(
        soup.find_all(["table", "dl", "ol", "ul"])
        or soup.find_all(attrs={"itemtype": True})
    )


def chunk_text(
    text: str,
    max_tokens: int = 3000,
    overlap_tokens: int = 100,
) -> list[TextChunk]:
    """Split text on semantic boundaries with overlap (PDF §5.2).

    Splits on paragraph/section boundaries, not fixed character count.
    Each chunk capped at 70% of the target model's context window
    to leave room for system prompt and schema instructions.
    """
    if not text:
        return []

    # Check if it fits in one chunk
    total_tokens = estimate_tokens(text)
    if total_tokens <= max_tokens:
        return [TextChunk(
            text=text,
            token_count=total_tokens,
            chunk_index=0,
            total_chunks=1,
        )]

    # Split on semantic boundaries
    paragraphs = re.split(r"\n\n+", text)
    chunks: list[TextChunk] = []
    current_text = ""
    current_tokens = 0

    for para in paragraphs:
        para_tokens = estimate_tokens(para)

        if current_tokens + para_tokens > max_tokens and current_text:
            chunks.append(TextChunk(
                text=current_text.strip(),
                token_count=current_tokens,
                chunk_index=len(chunks),
                total_chunks=0,  # Set after all chunks created
            ))

            # Overlap: keep last bit of previous chunk
            overlap_text = current_text[-overlap_tokens * 4:] if overlap_tokens else ""
            current_text = overlap_text + "\n\n" + para
            current_tokens = estimate_tokens(current_text)
        else:
            current_text += "\n\n" + para if current_text else para
            current_tokens += para_tokens

    # Last chunk
    if current_text.strip():
        chunks.append(TextChunk(
            text=current_text.strip(),
            token_count=current_tokens,
            chunk_index=len(chunks),
            total_chunks=0,
        ))

    # Set total_chunks
    for chunk in chunks:
        chunk.total_chunks = len(chunks)

    return chunks
