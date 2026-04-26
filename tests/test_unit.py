"""Unit tests for parameter encoding, response normalization, and validation.

Run with:  uv run pytest tests/ -v
"""

from __future__ import annotations

import json
import pathlib
from unittest.mock import AsyncMock, patch

import pytest

from stackchat.normalize import normalize_browse_entries, normalize_doc, normalize_facets
from stackchat.validate import normalize_isbn, normalize_issn

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


# ── ISBN validation ────────────────────────────────────────────────────────────


class TestISBNValidation:
    def test_valid_isbn13_no_hyphens(self):
        # Introduction to Algorithms, 3rd ed — verified valid ISBN-13
        normalized, err = normalize_isbn("9780262035613")
        assert err is None
        assert normalized == "9780262035613"

    def test_valid_isbn13_with_hyphens(self):
        normalized, err = normalize_isbn("978-0-262-03561-3")
        assert err is None
        assert normalized == "9780262035613"

    def test_valid_isbn10(self):
        normalized, err = normalize_isbn("0198534531")
        assert err is None
        assert normalized == "0198534531"

    def test_valid_isbn10_with_x(self):
        # Knuth TAOCP vol 1 — valid ISBN-10 with X check digit
        normalized, err = normalize_isbn("020161622X")
        assert err is None
        assert normalized == "020161622X"

    def test_valid_isbn10_with_hyphens(self):
        normalized, err = normalize_isbn("0-19-853453-1")
        assert err is None
        assert normalized == "0198534531"

    def test_invalid_isbn13_bad_check(self):
        _, err = normalize_isbn("9780198534530")  # wrong last digit
        assert err is not None
        assert "check digit" in err.lower()

    def test_invalid_isbn10_bad_check(self):
        _, err = normalize_isbn("0198534530")  # wrong last digit
        assert err is not None
        assert "check digit" in err.lower()

    def test_garbage_input(self):
        _, err = normalize_isbn("not-an-isbn")
        assert err is not None

    def test_empty_input(self):
        _, err = normalize_isbn("")
        assert err is not None


# ── ISSN validation ────────────────────────────────────────────────────────────


class TestISSNValidation:
    def test_valid_issn_with_hyphen(self):
        normalized, err = normalize_issn("0028-0836")  # Nature
        assert err is None
        assert normalized == "0028-0836"

    def test_valid_issn_no_hyphen(self):
        normalized, err = normalize_issn("00280836")
        assert err is None
        assert normalized == "0028-0836"

    def test_valid_issn_check_x(self):
        # ISSN "1234-561X": verified check digit = X
        # Sum: 1*8+2*7+3*6+4*5+5*4+6*3+1*2 = 8+14+18+20+20+18+2 = 100; 100%11=1 → check=10=X
        normalized, err = normalize_issn("1234-561X")
        assert err is None
        assert normalized == "1234-561X"

    def test_invalid_issn_bad_check(self):
        _, err = normalize_issn("0028-0830")  # wrong check digit
        assert err is not None
        assert "check digit" in err.lower()

    def test_garbage_input(self):
        _, err = normalize_issn("not-issn")
        assert err is not None

    def test_empty_input(self):
        _, err = normalize_issn("")
        assert err is not None


# ── Normalize doc ─────────────────────────────────────────────────────────────


class TestNormalizeDoc:
    def _make_doc(self, **attrs):
        return {
            "id": "9999999999999",
            "type": "Document",
            "attributes": attrs,
            "links": {"self": "https://catalog.princeton.edu/catalog/9999999999999"},
        }

    def _wrap(self, value, label="Field"):
        """Wrap a value in the Blacklight document_value envelope."""
        return {"type": "document_value", "attributes": {"value": value, "label": label}}

    def test_basic_fields(self):
        doc = self._make_doc(
            title="Plasma Physics",
            author_display=self._wrap(["Smith, John"], "Author"),
            format=self._wrap(["Book"], "Format"),
            pub_created_display=self._wrap("1987", "Published"),
            language_facet=None,
        )
        result = normalize_doc(doc)
        assert result.id == "9999999999999"
        assert result.title == "Plasma Physics"
        assert result.authors == ["Smith, John"]
        assert result.format == ["Book"]
        assert result.pub_date == "1987"
        assert "catalog.princeton.edu" in result.url

    def test_wrapped_title_display(self):
        doc = self._make_doc(
            title_display=self._wrap("Wrapped Title", "Title Display"),
        )
        result = normalize_doc(doc)
        assert result.title == "Wrapped Title"

    def test_missing_title_fallback(self):
        doc = self._make_doc()
        result = normalize_doc(doc)
        assert result.title == "Unknown title"

    def test_url_from_links(self):
        doc = self._make_doc(title="Test")
        doc["links"]["self"] = "https://catalog.princeton.edu/catalog/123"
        result = normalize_doc(doc)
        assert result.url == "https://catalog.princeton.edu/catalog/123"

    def test_url_fallback_when_no_links(self):
        doc = self._make_doc(title="Test")
        doc["links"] = {}
        result = normalize_doc(doc)
        assert "9999999999999" in result.url

    def test_raw_preserved(self):
        doc = self._make_doc(title="Test", some_solr_field="value")
        result = normalize_doc(doc)
        assert result.raw.get("some_solr_field") == "value"


# ── Normalize facets ──────────────────────────────────────────────────────────


class TestNormalizeFacets:
    def _make_facet_included(self, field: str, items: list[dict]) -> dict:
        # Real Blacklight shape: type="facet", items are JSON:API nodes
        return {
            "id": field,
            "type": "facet",
            "attributes": {
                "items": [
                    {"attributes": {"value": i["value"], "hits": i["hits"]}, "links": {}}
                    for i in items
                ]
            },
        }

    def test_basic_facet_extraction(self):
        included = [
            self._make_facet_included(
                "format",
                [{"value": "Book", "hits": 100}, {"value": "Journal", "hits": 50}],
            ),
            self._make_facet_included(
                "language_facet",
                [{"value": "English", "hits": 80}],
            ),
        ]
        facets = normalize_facets(included, ["format", "language_facet"])
        assert "format" in facets
        assert len(facets["format"]) == 2
        assert facets["format"][0].value == "Book"
        assert facets["format"][0].count == 100
        assert "language_facet" in facets

    def test_desired_fields_filter(self):
        included = [
            self._make_facet_included("format", [{"value": "Book", "hits": 10}]),
            self._make_facet_included("location", [{"value": "Firestone", "hits": 5}]),
        ]
        facets = normalize_facets(included, ["format"])
        assert "format" in facets
        assert "location" not in facets

    def test_empty_included(self):
        facets = normalize_facets([], ["format"])
        assert facets == {}

    def test_non_facet_items_ignored(self):
        included = [
            {"id": "sort_field", "type": "sort", "attributes": {}},
            self._make_facet_included("format", [{"value": "Book", "hits": 10}]),
        ]
        facets = normalize_facets(included, ["format"])
        assert "format" in facets
        assert "sort_field" not in facets


# ── Browse normalization ──────────────────────────────────────────────────────


class TestNormalizeBrowse:
    def test_browse_entries(self):
        raw = [
            {"id": 1, "label": "Beethoven", "count": 324, "dir": "ltr"},
            {"id": 2, "label": "Beethoven, Ludwig van", "count": 100, "dir": "ltr"},
        ]
        entries = normalize_browse_entries(raw)
        assert len(entries) == 2
        assert entries[0].label == "Beethoven"
        assert entries[0].count == 324
        assert entries[0].direction == "ltr"

    def test_empty_browse(self):
        entries = normalize_browse_entries([])
        assert entries == []

    def test_rtl_entry(self):
        raw = [{"id": 99, "label": "العربية", "count": 5, "dir": "rtl"}]
        entries = normalize_browse_entries(raw)
        assert entries[0].direction == "rtl"
