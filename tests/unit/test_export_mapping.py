"""Tests for export/mapping.py — tab headers, field order, and lookup functions."""
from __future__ import annotations

from provenmesh.export.mapping import (
    FIELD_ORDER,
    RECORD_TYPE_TO_TAB,
    TAB_HEADERS,
    get_field_order,
    get_headers,
    get_tab_name,
)


class TestTabHeaders:
    def test_all_tabs_present(self) -> None:
        assert "Startups" in TAB_HEADERS
        assert "Products" in TAB_HEADERS
        assert "Papers" in TAB_HEADERS
        assert "Jobs" in TAB_HEADERS
        assert "News" in TAB_HEADERS
        assert "Entity Mapping Log" in TAB_HEADERS

    def test_headers_are_lists(self) -> None:
        for tab, headers in TAB_HEADERS.items():
            assert isinstance(headers, list), f"{tab} headers not a list"
            assert len(headers) > 0, f"{tab} has no headers"

    def test_common_columns(self) -> None:
        for tab in ["Startups", "Products", "Papers", "Jobs", "News"]:
            headers = TAB_HEADERS[tab]
            assert "Canonical ID" in headers
            assert "Entity Name" in headers
            assert "Record Type" in headers


class TestFieldOrder:
    def test_all_record_types(self) -> None:
        for rt in ["STARTUP", "PRODUCT", "PAPER", "JOB", "NEWS_SIGNAL"]:
            assert rt in FIELD_ORDER
            assert len(FIELD_ORDER[rt]) > 0


class TestGetHeaders:
    def test_known_tab(self) -> None:
        headers = get_headers("Startups")
        assert len(headers) > 5
        assert "Entity Name" in headers

    def test_unknown_tab(self) -> None:
        assert get_headers("NonExistent") == []


class TestGetFieldOrder:
    def test_known_type(self) -> None:
        fields = get_field_order("STARTUP")
        assert "description" in fields
        assert "website" in fields

    def test_unknown_type(self) -> None:
        assert get_field_order("UNKNOWN") == []


class TestGetTabName:
    def test_all_mappings(self) -> None:
        assert get_tab_name("STARTUP") == "Startups"
        assert get_tab_name("PRODUCT") == "Products"
        assert get_tab_name("PAPER") == "Papers"
        assert get_tab_name("JOB") == "Jobs"
        assert get_tab_name("NEWS_SIGNAL") == "News"

    def test_unknown_type(self) -> None:
        assert get_tab_name("UNKNOWN") == "Unknown"

    def test_record_type_to_tab_complete(self) -> None:
        assert len(RECORD_TYPE_TO_TAB) == 5
