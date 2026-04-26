"""Tests against captured fixture data (no live network calls).

These test normalization of real catalog response shapes.
"""

from __future__ import annotations

import pytest

from stackchat.normalize import (
    normalize_doc,
    normalize_facets,
    normalize_record_response,
)
from stackchat.fields import DEFAULT_RESPONSE_FACETS


class TestSearchFixture:
    def test_total_count(self, search_fixture):
        total = search_fixture["meta"]["pages"]["total_count"]
        assert total > 0

    def test_normalize_first_doc(self, search_fixture):
        doc = search_fixture["data"][0]
        result = normalize_doc(doc)
        assert result.id
        assert result.title != "Unknown title"
        assert result.url.startswith("https://catalog.princeton.edu/catalog/")

    def test_format_is_list(self, search_fixture):
        doc = search_fixture["data"][0]
        result = normalize_doc(doc)
        assert isinstance(result.format, list)

    def test_facets_from_search(self, search_fixture):
        included = search_fixture.get("included", [])
        facets = normalize_facets(included, DEFAULT_RESPONSE_FACETS)
        # At minimum access_facet and format should be present in search
        assert len(facets) > 0

    def test_empty_result(self, empty_fixture):
        total = empty_fixture["meta"]["pages"]["total_count"]
        assert total == 0
        docs = empty_fixture.get("data", [])
        assert docs == []


class TestRecordFixture:
    def test_normalize_record(self, record_fixture):
        result = normalize_record_response(record_fixture)
        assert result.found is True
        assert result.id == "9987870933506421"

    def test_record_has_url(self, record_fixture):
        result = normalize_record_response(record_fixture)
        assert "catalog.princeton.edu" in result.url

    def test_not_found_record(self):
        result = normalize_record_response({})
        assert result.found is False


class TestFacetFixture:
    def test_facet_has_items(self, facet_fixture):
        items = facet_fixture["response"]["facets"]["items"]
        assert len(items) > 0

    def test_facet_book_present(self, facet_fixture):
        items = facet_fixture["response"]["facets"]["items"]
        values = [i["value"] for i in items]
        assert "Book" in values

    def test_facet_hits_are_positive(self, facet_fixture):
        items = facet_fixture["response"]["facets"]["items"]
        for item in items:
            assert item["hits"] > 0
