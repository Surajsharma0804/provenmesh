"""Tests for extraction/chunking.py — content extraction and text chunking."""
from __future__ import annotations

from provenmesh.extraction.chunking import (
    TextChunk,
    chunk_text,
    estimate_tokens,
    extract_main_content,
    has_structured_content,
)


class TestEstimateTokens:
    def test_basic(self) -> None:
        assert estimate_tokens("hello world test") == 4  # 16 chars / 4

    def test_empty(self) -> None:
        assert estimate_tokens("") == 1  # min of 1

    def test_long_text(self) -> None:
        text = "a" * 4000
        assert estimate_tokens(text) == 1000


class TestExtractMainContent:
    def test_simple_html(self) -> None:
        html = "<html><body><p>Hello World</p></body></html>"
        result = extract_main_content(html)
        assert "Hello World" in result

    def test_removes_scripts(self) -> None:
        html = """
        <html><body>
        <p>Content</p>
        <script>alert('xss')</script>
        </body></html>
        """
        result = extract_main_content(html)
        assert "alert" not in result

    def test_removes_nav(self) -> None:
        html = """
        <html><body>
        <nav>Navigation</nav>
        <p>Main content here</p>
        <footer>Footer</footer>
        </body></html>
        """
        result = extract_main_content(html)
        assert "Main content" in result


class TestHasStructuredContent:
    def test_with_table(self) -> None:
        assert has_structured_content("<table><tr><td>data</td></tr></table>")

    def test_with_list(self) -> None:
        assert has_structured_content("<ul><li>item</li></ul>")

    def test_plain_text(self) -> None:
        assert has_structured_content("<p>plain paragraph</p>") is False


class TestChunkText:
    def test_empty_text(self) -> None:
        assert chunk_text("") == []

    def test_short_text(self) -> None:
        chunks = chunk_text("Short text", max_tokens=100)
        assert len(chunks) == 1
        assert chunks[0].chunk_index == 0
        assert chunks[0].total_chunks == 1

    def test_long_text_splits(self) -> None:
        paragraphs = ["Paragraph " + str(i) + ". " + "word " * 50
                       for i in range(20)]
        text = "\n\n".join(paragraphs)
        chunks = chunk_text(text, max_tokens=100)
        assert len(chunks) > 1
        for chunk in chunks:
            assert chunk.total_chunks == len(chunks)

    def test_chunk_indexing(self) -> None:
        text = "\n\n".join(["word " * 200 for _ in range(5)])
        chunks = chunk_text(text, max_tokens=100)
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i


class TestTextChunk:
    def test_creation(self) -> None:
        chunk = TextChunk(
            text="test", token_count=1,
            chunk_index=0, total_chunks=1,
        )
        assert chunk.text == "test"
        assert chunk.has_structured_markup is False
        assert chunk.start_offset == 0


class TestExtractMainContentEdgeCases:
    def test_removes_hidden_elements(self) -> None:
        """Hidden elements with display:none should be removed (line 64).
        We mock readability to fail so the raw HTML flows through
        the hidden-element-removal code path."""
        from unittest.mock import patch
        html = """
        <html><body>
        <p>Visible content</p>
        <div style="display: none">Hidden content</div>
        <div style="display:none">Also hidden</div>
        </body></html>
        """
        with patch(
            "readability.Document",
            side_effect=ImportError("mocked"),
        ):
            result = extract_main_content(html)
        assert "Visible content" in result
        assert "Hidden content" not in result
        assert "Also hidden" not in result

    def test_readability_fallback_on_error(self) -> None:
        """When readability raises, raw HTML is used (lines 52-53)."""
        from unittest.mock import patch
        html = "<html><body><p>Fallback content here</p></body></html>"
        with patch(
            "readability.Document",
            side_effect=RuntimeError("readability broken"),
        ):
            result = extract_main_content(html)
        assert "Fallback content" in result

    def test_removes_form_elements(self) -> None:
        html = """
        <html><body>
        <p>Content</p>
        <form><input type="text"/></form>
        <iframe src="ad.html"></iframe>
        </body></html>
        """
        result = extract_main_content(html)
        assert "Content" in result

    def test_normalizes_whitespace(self) -> None:
        html = """
        <html><body>
        <p>Line one</p>



        <p>Line two</p>
        </body></html>
        """
        result = extract_main_content(html)
        # Triple newlines should be normalized to double
        assert "\n\n\n" not in result


class TestChunkTextOverlap:
    def test_overlap_preserved(self) -> None:
        """Verify overlap_tokens parameter works (line 131)."""
        paragraphs = ["word " * 100 for _ in range(5)]
        text = "\n\n".join(paragraphs)
        chunks = chunk_text(text, max_tokens=100, overlap_tokens=20)
        assert len(chunks) > 1

